# Which Situations Make AI Agents Break Rules? Data and code

Code and data for the paper "Which Situations Make AI Agents Break Rules? A
Preregistered Measurement Study" (Amirapu and Gupta, 2026).

The study measures how often AI agents deliberately open a forbidden folder
(`/restricted`) inside an offline Docker container, and which situations raise
that rate. It covers 20,182 runs across twelve open-weight models and one
closed model.

## What is where

| Folder or file | What it holds |
| --- | --- |
| `breach-risk/` | The test harness (Docker sandbox, agent loop, scenarios, scorer) and the analysis scripts |
| `breach-risk/data/` | Raw, unaggregated run records for every study, plus logs and hand-coding files |
| `breach-risk/data/PREREGISTRATION.md` | The preregistration and its amendments |
| `paper_data_pack/` | The tables and figures' underlying numbers used in the paper, with a README explaining each file |
| `LICENSE` | MIT licence for the code |
| `LICENSE-DATA.md` | CC BY 4.0 licence for the data |

## Using it

1. Read `paper_data_pack/README.md` to find the file behind each table in the paper.
2. The scripts `paper_pack_a.py` and `paper_pack_b.py` in `breach-risk/` build those tables from the raw records.
3. To rerun the experiments you need Docker and API access to the models. Put keys in environment variables and copy `models.example.json` to your own config. Never commit keys.

## Citation

Amirapu, K. and Gupta, C. P. (2026). Which Situations Make AI Agents Break Rules? A Preregistered Measurement Study.
