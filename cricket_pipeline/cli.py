import argparse
import sys

from cricket_pipeline import dataset, pipeline
from cricket_pipeline.config import dataset_csv, work_dir


def status(args) -> int:
    pipeline.fetch_archives(download=not args.no_download)
    known = dataset.known_match_ids(dataset_csv())
    new = pipeline.find_new_matches(known)
    print(f"{len(known)} matches in the dataset")
    for source, ids in new.items():
        print(f"  {source.archive:<6} {len(ids):>5} new")
    print(f"  total  {sum(len(ids) for ids in new.values()):>5} new")
    return 0


def ingest(args) -> int:
    pipeline.fetch_archives(download=not args.no_download)
    known = set() if args.from_scratch else dataset.known_match_ids(dataset_csv())
    new = pipeline.find_new_matches(known)
    all_failures = {}
    total_rows = 0
    for source, ids in new.items():
        ids = ids[: args.limit] if args.limit else ids
        if not ids:
            continue
        rows, failures, tables = pipeline.build_rows(source, ids)
        # One file per archive keeps memory small and a bad archive from losing the rest
        output = work_dir() / f"cricsheet_{source.archive}.csv"
        rows.to_csv(output, index=False)
        for name, table in tables.items():
            table.to_csv(work_dir() / f"cricsheet_{source.archive}_{name}.csv", index=False)
        total_rows += len(rows)
        print(f"  {source.archive:<6} {len(ids) - len(failures):>5} matches, {len(rows):>8} rows, {len(failures)} failed")
        all_failures.update(failures)
    print(f"{total_rows} rows written to {work_dir()}")
    for match_id, reason in all_failures.items():
        print(f"  FAILED {match_id}: {reason}")
    return 1 if all_failures else 0


def player_ids(args) -> int:
    from cricket_pipeline import players

    found = players.write_player_ids()
    missing = found["cricinfo_id"].isna().sum()
    print(f"{len(found)} players, {missing} without a Cricinfo id")
    return 0


def players(args) -> int:
    from cricket_pipeline import scrape_players

    return scrape_players.run(limit=args.limit)


def matches(args) -> int:
    from cricket_pipeline import scrape_matches

    return scrape_matches.run([int(i) for i in args.ids], redo=args.redo)


def capture(args) -> int:
    from cricket_pipeline import scrape_matches

    return scrape_matches.run_queue(limit=args.limit, worker=args.worker, workers=args.workers)


def check(args) -> int:
    from cricket_pipeline import checks

    return checks.run()


def build(args) -> int:
    from cricket_pipeline import build as build_module

    totals = build_module.build(archives=args.archives)
    print(f"wrote {totals['rows']:,} rows for {totals['matches']:,} matches ({totals['captured']:,} with a Cricinfo capture) to {build_module.output_dir()}")
    print(f"matches to look at in review.csv: {totals['review']:,}")
    return 0


def verify(args) -> int:
    from cricket_pipeline import verify as verify_module

    pipeline.fetch_archives(download=False)
    return verify_module.run(args.sample, args.seed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cricket_pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, handler in (("status", status), ("ingest", ingest)):
        sub = commands.add_parser(name)
        sub.add_argument("--no-download", action="store_true", help="reuse archives already on disk")
        if name == "ingest":
            sub.add_argument("--limit", type=int, help="only build this many matches per archive")
            sub.add_argument("--from-scratch", action="store_true", help="ignore the published dataset and build every match")
        sub.set_defaults(handler=handler)

    sub = commands.add_parser("player-ids")
    sub.set_defaults(handler=player_ids)

    sub = commands.add_parser("players")
    sub.add_argument("--limit", type=int, help="fetch only this many profiles")
    sub.set_defaults(handler=players)

    sub = commands.add_parser("matches")
    sub.add_argument("ids", nargs="+", help="Cricinfo and Cricsheet match ids")
    sub.add_argument("--redo", action="store_true", help="capture again even if already saved")
    sub.set_defaults(handler=matches)

    sub = commands.add_parser("capture")
    sub.add_argument("--limit", type=int, help="capture only this many matches this run")
    sub.add_argument("--worker", type=int, default=0, help="this worker's number, from 0 (for two workers, run 0 and 1)")
    sub.add_argument("--workers", type=int, default=1, help="how many workers share the queue")
    sub.set_defaults(handler=capture)

    sub = commands.add_parser("build")
    sub.add_argument("--archives", nargs="+", help="only these Cricsheet archives, for a quick test (for example wpl ipl)")
    sub.set_defaults(handler=build)

    sub = commands.add_parser("check", help="check the built files for broken keys, links and totals")
    sub.set_defaults(handler=check)

    sub = commands.add_parser("verify")
    sub.add_argument("--sample", type=int, default=100)
    sub.add_argument("--seed", type=int, default=1)
    sub.set_defaults(handler=verify)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
