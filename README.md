# ChainBeeT Updater

Downloads and verifies the ChainBeeT asset updates described by the remote Android manifest.

## Usage

Install the dependency, then run the updater:

```bash
pip install requests
python main.py
```

Assets are written to `assets/` by default. Use another directory when needed:

```bash
python main.py --directory path/to/assets
```
