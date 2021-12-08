# alga: 

![GitHub commit activity](https://img.shields.io/github/commit-activity/w/johnifx/alga) ![GitHub tag (latest by date)](https://img.shields.io/github/v/tag/johnifx/alga) ![GitHub all releases](https://img.shields.io/github/downloads/johnifx/alga/total)

This repo uses oanda v20 API as a basis for a forex trading algo. The focus is not on some magic indicators but to implement more and more general trading rules like " do not add to loser" or "let your winners run and cut your losses quickly".

The repository does not include the defs.py file which contains the API key.

Some additional ipynb jupyter notebook files also included. They contain background analysis, and not part of the algo.

Unfortunately the algo is not successful, still producing losses, so it may be called loss generator or account destroyer.  I have way to many ideas to implement but time is a constraint.

cfg.py: this is a general purpose file. it runs the streaming prices, transactions and account polling in the background and also provides variables available for all other classes.

main.py: this is where account management happens, trader.py this class is responsible for the trading functions, quant.py this is the market based analysis, technical analysis and signal generator.
