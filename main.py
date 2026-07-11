import argparse
from pathlib import Path

from updater import check_update, do_update


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Check for and install ChainBeeT asset updates.'
    )
    parser.add_argument(
        '-d',
        '--directory',
        default='assets',
        help='Directory where updated assets are stored (default: assets).',
    )
    args = parser.parse_args()
    target_directory = Path(args.directory)

    if not check_update(target_directory):
        print('Assets are already up to date.')
        return 0

    print(f'Updating assets in {target_directory}...')
    if do_update(target_directory):
        print('Update completed successfully.')
        return 0

    print('Update failed.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
