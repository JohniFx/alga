#!/usr/bin/python3

from datetime import datetime
with open('changelog', 'a' ) as file:
    file.write(f'{datetime.now()} changelog')