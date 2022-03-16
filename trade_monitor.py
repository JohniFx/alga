#!/usr/bin/python3

from datetime import datetime
import os

cp = os.path.dirname(os.path.abspath(__file__))

with open(f'{cp}/changelog', 'a' ) as file:
    file.write(f'\n{datetime.now()} changelog')
    print(datetime.now(), 'change log updated')