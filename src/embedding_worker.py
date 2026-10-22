"""Private inference worker; closing stdin releases all native model allocations."""
import json, sys
from models import create_embedder

def main():
    model = create_embedder(sys.argv[1])
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request['kind'] == 'query': values = model.query_embed(request['query'])
            else: values = model.passage_embed(request['texts'], batch_size=16)
            result = {'vectors': [v.tolist() for v in values]}
        except Exception as exc:
            result = {'error': str(exc)}
        print(json.dumps(result), flush=True)
if __name__ == '__main__': main()
