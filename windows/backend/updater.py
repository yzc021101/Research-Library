"""GitHub release updater. State and downloads stay in the user's library.

Install is an explicit desktop action. Complete bundles are staged beside the
old app and swapped only after the desktop and updater processes have exited.
No in-place executable writes, privilege escalation or execution-policy edits.
"""
from pathlib import Path, PurePosixPath
import argparse, base64, contextlib, hashlib, json, os, plistlib, re, shutil, ssl, stat, subprocess, sys, time, urllib.request, uuid, zipfile
import certifi
from paths import ROOT
from components import HTTPSOnly

REPO = 'https://github.com/yzc021101/Research-Library'
API = 'https://api.github.com/repos/yzc021101/Research-Library/releases/latest'
HOME = ROOT/'updates'
STATE = HOME/'state.json'
MAX_ARCHIVE = 1024**3
MAX_EXPANDED = 4*1024**3

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        # A Windows reader can briefly deny replacement of an open file.
        # Keep the previous complete state until the atomic swap succeeds.
        for attempt in range(20):
            try:
                os.replace(tmp,path)
                break
            except PermissionError:
                if attempt==19:raise
                time.sleep(.05)
    finally:
        tmp.unlink(missing_ok=True)

def read(path, default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):return {} if default is None else default

def state(**changes):
    s=read(STATE);s.update(changes);write(STATE,s);return s

def version(text):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',text)
    if not match:raise ValueError('仅接受正式的三段版本号')
    return tuple(map(int,match.groups()))

def asset_name():return 'research_library-windows-x64.zip' if os.name=='nt' else 'research_library-macos-arm64.dmg'

def opener():return urllib.request.build_opener(HTTPSOnly(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

def fetch_release():
    req=urllib.request.Request(API,headers={'User-Agent':'research_library-updater','Accept':'application/vnd.github+json'})
    with opener().open(req,timeout=30) as res:
        raw=res.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('版本信息过大')
    return json.loads(raw)

def release_asset(data):
    tag=data['tag_name'];version(tag)
    if data.get('draft') or data.get('prerelease'):raise ValueError('忽略草稿和预发布版本')
    name=asset_name();items=[a for a in data['assets'] if a['name']==name and a.get('state')=='uploaded']
    if len(items)!=1:raise ValueError('此版本尚未提供适合本机的安装包')
    a=items[0];url=REPO+'/releases/download/'+tag+'/'+name
    if a['browser_download_url']!=url:raise ValueError('安装包地址不属于官方发布仓库')
    digest=a.get('digest','')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('发布包缺少 SHA-256，请稍后重试')
    if type(a['size']) is not int or not 0<a['size']<=MAX_ARCHIVE:raise ValueError('安装包大小异常')
    return {'version':tag.removeprefix('v'),'url':url,'size':a['size'],'sha256':digest[7:],'name':name,'release_url':REPO+'/releases/tag/'+tag,'notes':str(data.get('body',''))[:20000]}

def check(current, automatic=False):
    version(current)
    old=read(STATE)
    if automatic and time.time()-old.get('checked_at',0)<24*3600:return old
    state(phase='checking',error='')
    try:item=release_asset(fetch_release())
    except Exception as e:
        # Startup may check while offline. Keep the already verified package
        # actionable and report the check failure without replacing its state.
        cached=old.get('release',{})
        if downloaded(cached) and version(cached['version'])>version(current):
            return state(phase='ready',current=current,done=cached['size'],total=cached['size'],message='更新已下载；暂时无法检查最新版本',error=str(e))
        raise
    newer=version(item['version'])>version(current)
    # Release notes can change without changing the package. Recover a verified
    # completed download even if a previous check or process exit changed phase.
    ready=same_archive(old.get('release',{}),item) and downloaded(item)
    return state(phase=('ready' if ready else 'available') if newer else 'current',release=item,current=current,checked_at=time.time(),error='',message=('发现新版本 '+item['version']) if newer else '已是最新版本')

def cancelled():
    if (HOME/'cancel').exists():raise InterruptedError('下载已取消')

def verify_archive(path,item):
    if path.stat().st_size!=item['size']:raise ValueError('更新包大小不符')
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    if h.hexdigest()!=item['sha256']:raise ValueError('更新包校验失败，未修改当前 App')

def same_archive(a,b):
    return all(a.get(key)==b.get(key) for key in ('version','name','size','sha256'))

def downloaded(item):
    try:
        if item.get('name')!=asset_name():return False
        version(item['version'])
        if type(item['size']) is not int or not 0<item['size']<=MAX_ARCHIVE:return False
        if not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):return False
        verify_archive(HOME/item['name'],item)
        return True
    except (OSError,KeyError,TypeError,ValueError):return False

def download(current):
    item=release_asset(fetch_release()) # Do not trust a persisted or edited download URL.
    if version(item['version'])<=version(current):return state(phase='current',message='已是最新版本',error='')
    if shutil.disk_usage(HOME).free<item['size']+MAX_EXPANDED:raise ValueError('更新需要至少 5 GB 可用空间用于下载和完整性检查')
    (HOME/'cancel').unlink(missing_ok=True)
    path=HOME/item['name'];temp=HOME/(item['name']+'.part')
    state(phase='downloading',release=item,current=current,done=0,total=item['size'],transaction_id=None,error='',message='正在下载更新')
    try:
        request=urllib.request.Request(item['url'],headers={'User-Agent':'research_library-updater'})
        with opener().open(request,timeout=30) as res,temp.open('wb') as out:
            count=0;last=0
            while b:=res.read(1024*1024):
                cancelled();count+=len(b)
                if count>item['size']:raise ValueError('更新包超出预期大小')
                out.write(b)
                if time.monotonic()-last>.5:state(done=count);last=time.monotonic()
        cancelled();state(phase='verifying',done=count,message='下载完成，正在校验完整性');verify_archive(temp,item);os.replace(temp,path)
        return state(phase='ready',done=item['size'],message='更新已下载，安装并重启后生效',error='')
    finally:temp.unlink(missing_ok=True)

def validate_app(path, expected=None):
    if os.name=='nt':
        data=read(path/'distribution.json');v=data.get('version','');version(v)
        for name in ['ResearchLibrary.Windows.exe','engine/research-library-engine.exe']:
            if not (path/name).is_file():raise ValueError('更新缺少必需程序')
    else:
        with (path/'Contents/Info.plist').open('rb') as f:data=plistlib.load(f)
        if data.get('CFBundleIdentifier')!='local.research.library.lab':raise ValueError('更新包应用标识不符')
        v=data.get('CFBundleShortVersionString','');version(v)
        if not (path/'Contents/Resources/engine/research-library-engine').is_file():raise ValueError('更新缺少运行环境')
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    if expected is not None and v!=expected:raise ValueError('安装包内版本与发布版本不一致')
    return v

def extract_zip(archive, dest):
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist())>MAX_EXPANDED:raise ValueError('更新包解压体积异常')
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or stat.S_ISLNK(i.external_attr>>16):raise ValueError('更新包包含不安全路径')
            if not p.parts or p.parts[0]!='research_library':raise ValueError('更新包目录结构不符')
        z.extractall(dest)
    return dest/'research_library'

def prepare(target):
    target=target.absolute()
    if target.is_symlink():raise ValueError('请从真实安装目录进行升级')
    if ROOT.resolve().is_relative_to(target.resolve()):raise ValueError('资料库位于应用目录内，请先移出资料库或手动升级，避免覆盖资料')
    if os.name=='nt':
        manifest=read(target/'distribution-files.json',[])
        if not isinstance(manifest,list) or not manifest:raise ValueError('此旧版缺少安装文件清单，请手动升级一次')
        expected=set(manifest)|{'distribution-files.json'}
        actual={p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
        if actual-expected:raise ValueError('安装目录含额外文件，请先移出这些文件或手动升级；当前文件未改动')
    current=validate_app(target)
    s=read(STATE);item=release_asset(fetch_release())
    if s.get('phase')!='ready' or not same_archive(s.get('release',{}),item):raise ValueError('发布版本已变化，请重新检查并下载')
    if version(item['version'])<=version(current):raise ValueError('不允许降级或重复安装')
    archive=HOME/item['name'];verify_archive(archive,item)
    if not os.access(target.parent,os.W_OK):raise ValueError('安装目录不可写，请从发布页下载安装包并手动替换')
    if str(target).startswith('/Volumes/'):raise ValueError('请先将 App 安装到应用程序文件夹，再进行升级')
    stage=target.parent/('.research-library-update-'+uuid.uuid4().hex)
    backup=target.parent/('.research-library-previous-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        state(phase='preparing',message='正在验证并准备安装',error='')
        if os.name=='nt':
            unpacked=extract_zip(archive,stage)
        else:
            mount=HOME/('mount-'+uuid.uuid4().hex);mount.mkdir()
            try:
                subprocess.run(['/usr/bin/hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(archive)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                source=mount/'投研纵览.app';validate_app(source,item['version'])
                unpacked=stage/'投研纵览.app'
                subprocess.run(['/usr/bin/ditto',str(source),str(unpacked)],check=True)
            finally:
                subprocess.run(['/usr/bin/hdiutil','detach',str(mount)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                with contextlib.suppress(OSError):mount.rmdir()
        validate_app(unpacked,item['version'])
        journal={'id':uuid.uuid4().hex,'target':str(target),'stage':str(stage),'unpacked':str(unpacked),'backup':str(backup),'version':item['version'],'archive':str(archive),'release':item}
        write(HOME/'transaction.json',journal)
        state(phase='prepared',transaction_id=journal['id'],message='已准备，等待 App 重启')
        return journal
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise

def ps_quote(text):return "'"+str(text).replace("'","''")+"'"

def launch_helper(j, desktop_pid):
    if desktop_pid<=0 or desktop_pid==os.getpid():raise ValueError('无效 App 进程')
    result=HOME/'install-result.json';result.unlink(missing_ok=True)
    # EncodedCommand transports literal paths; it does not change PowerShell policy.
    if os.name=='nt':
        script="""$ErrorActionPreference='Stop'
$t=@@TARGET@@;$s=@@STAGED@@;$b=@@BACKUP@@;$r=@@RESULT@@;$root=@@ROOT@@;$transaction=@@TRANSACTION@@
try {
 foreach($id in @(@@DESKTOP@@,@@WORKER@@)) {
  $deadline=[DateTime]::UtcNow.AddSeconds(90)
  while(Get-Process -Id $id -ErrorAction SilentlyContinue) {
   if([DateTime]::UtcNow -ge $deadline){throw 'App did not exit within 90 seconds'}
   Start-Sleep -Milliseconds 200
  }
 }
 Move-Item -LiteralPath $t -Destination $b
 try { Move-Item -LiteralPath $s -Destination $t } catch { Move-Item -LiteralPath $b -Destination $t; throw }
 [IO.File]::WriteAllText($r,(@{ok=$true;id=$transaction}|ConvertTo-Json))
 $env:RESEARCH_LIBRARY_ROOT=$root
 Start-Process -FilePath (Join-Path $t 'ResearchLibrary.Windows.exe') -WorkingDirectory $t
} catch { [IO.File]::WriteAllText($r,(@{ok=$false;id=$transaction;error=$_.Exception.Message}|ConvertTo-Json)); if(Test-Path -LiteralPath $t){Start-Process -FilePath (Join-Path $t 'ResearchLibrary.Windows.exe') -WorkingDirectory $t} }
"""
        values={'TARGET':ps_quote(j['target']),'STAGED':ps_quote(j['unpacked']),'BACKUP':ps_quote(j['backup']),'RESULT':ps_quote(result),'ROOT':ps_quote(ROOT),'TRANSACTION':ps_quote(j['id']),'DESKTOP':str(desktop_pid),'WORKER':str(os.getpid())}
        script=re.sub(r'@@([A-Z]+)@@',lambda match:values[match[1]],script)
        encoded=base64.b64encode(script.encode('utf-16-le')).decode()
        exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        subprocess.Popen([str(exe),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],cwd=HOME,creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        # Arguments, not string interpolation, carry all user-controlled paths.
        script='''target=$1; staged=$2; backup=$3; result=$4; desktop=$5; worker=$6; root=$7; transaction=$8
count=0
while kill -0 "$desktop" 2>/dev/null || kill -0 "$worker" 2>/dev/null; do
 count=$((count+1)); if [ "$count" -gt 90 ]; then printf '{"ok":false,"id":"%s","error":"App did not exit"}' "$transaction" > "$result"; exit 1; fi
 sleep 1
done
if ! /bin/mv "$target" "$backup"; then printf '{"ok":false,"id":"%s","error":"Cannot move old App"}' "$transaction" > "$result"; exit 1; fi
if ! /bin/mv "$staged" "$target"; then /bin/mv "$backup" "$target"; printf '{"ok":false,"id":"%s","error":"Install rolled back"}' "$transaction" > "$result"; /usr/bin/open -n "$target"; exit 1; fi
printf '{"ok":true,"id":"%s"}' "$transaction" > "$result"
RESEARCH_LIBRARY_ROOT="$root" /usr/bin/open -n "$target" --env "RESEARCH_LIBRARY_ROOT=$root"
'''
        subprocess.Popen(['/bin/sh','-c',script,'research-library-updater',j['target'],j['unpacked'],j['backup'],str(result),str(desktop_pid),str(os.getpid()),str(ROOT),j['id']],cwd=HOME,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def finish(target):
    journal_path=HOME/'transaction.json';result_path=HOME/'install-result.json'
    j=read(journal_path);result=read(result_path)
    if not j or str(target.absolute())!=j.get('target'):return
    # A helper still running or an unrelated result must never consume this
    # transaction. Legacy releases wrote neither ID, so migrate those once.
    if type(result.get('ok')) is not bool or j.get('id')!=result.get('id'):return
    installed=validate_app(target)
    complete=version(installed)>=version(j['version'])
    if result['ok'] and not complete:raise ValueError('更新后的应用版本不符，保留更新记录以便恢复')
    s=read(STATE);release=s.get('release',{})
    newer=bool(release) and version(release.get('version','0.0.0'))>version(j['version'])
    # Only clean generated siblings belonging to this exact transaction.
    cleanup=[]
    for key,prefix in [('backup','.research-library-previous-'),('stage','.research-library-update-')]:
        p=Path(j[key])
        if p.parent!=target.absolute().parent or not re.fullmatch(re.escape(prefix)+r'[0-9a-f]{32}',p.name) or p.is_symlink():raise ValueError('更新清理路径无效')
        cleanup.append(p)
    for p in cleanup:shutil.rmtree(p,ignore_errors=True)
    archive=Path(j['archive'])
    item=j.get('release',release)
    # Different releases intentionally reuse an asset name. Never delete a new
    # download merely because an older transaction used the same path.
    if complete and not newer and item.get('version')==j['version'] and archive.parent==HOME and archive.name==asset_name() and downloaded(item):
        archive.unlink(missing_ok=True)
    if not newer:
        if complete:
            state(phase='current',current=installed,transaction_id=None,message='已更新到 '+installed,error='')
        elif downloaded(item):
            state(phase='ready',current=installed,release=item,transaction_id=None,done=item['size'],total=item['size'],message='安装未完成，已保留下载，可再次安装',error=result.get('error','安装失败，已保留旧版'))
        else:
            state(phase='error',transaction_id=None,error=result.get('error','安装失败，已保留旧版'))
    # Consume the journal first: a crash between these unlinks cannot replay a
    # completed install on the next launch and overwrite newer download state.
    journal_path.unlink(missing_ok=True)
    result_path.unlink(missing_ok=True)

@contextlib.contextmanager
def lock():
    HOME.mkdir(parents=True,exist_ok=True)
    with (HOME/'update.lock').open('a+b') as f:
        try:
            if os.name=='nt':
                import msvcrt
                f.seek(0);f.write(b'0');f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise RuntimeError('已有更新任务正在运行')
        yield

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','download','install','finish']);p.add_argument('--current',default='0.6.11');p.add_argument('--target',type=Path);p.add_argument('--pid',type=int);p.add_argument('--automatic',action='store_true');a=p.parse_args()
    with lock():
        try:
            if a.action=='check':
                s=check(a.current,a.automatic)
                if a.automatic and s.get('phase')=='available':download(a.current)
            elif a.action=='download':download(a.current)
            elif a.action=='install':
                if not a.target or not a.pid:raise ValueError('缺少安装目标')
                j=prepare(a.target);launch_helper(j,a.pid)
            elif a.action=='finish':
                if a.target:finish(a.target)
        except Exception as e:
            state(phase='cancelled' if isinstance(e,InterruptedError) else 'error',error=str(e),message='更新未完成；当前 App 和资料保留')
            print(str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
