"""Process already collected public snapshots through normalization, chunking and embeddings."""
import argparse
import json
import sys
import catalog
import build_condition_drafts
import build_knowledge
import embedding_search

STEPS = ['Normalize collected snapshots', 'Refresh condition review drafts',
         'Version snapshots and split documents', 'Reuse unchanged vectors and embed pending text']


def refresh(limit=0):
    # Hold the same process lock through all stages; no simultaneous source-version changes.
    with embedding_search.build_lock():
        for number, (label, action) in enumerate(zip(STEPS,
                [catalog.build, build_condition_drafts.main, build_knowledge.build,
                 lambda: embedding_search.build_locked(limit)]), 1):
            print(f'[{number}/4] {label}', flush=True)
            action()
    return embedding_search.status()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Show stages without writing or making API requests')
    parser.add_argument('--limit', type=int, default=0, help='Maximum pending chunks to process; 0 means all')
    args = parser.parse_args()
    if args.limit < 0: parser.error('limit must be nonnegative')
    if args.plan:
        print(json.dumps({'steps':STEPS, 'network_requests':False, 'embedding_limit':args.limit}, indent=2))
        return
    try:
        print(json.dumps(refresh(args.limit), ensure_ascii=False, indent=2))
    except RuntimeError as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
