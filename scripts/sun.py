#!/bin/env python

import argparse
import datetime
import sys

from argparse import Namespace
from astral import Depression, LocationInfo
from astral.sun import sun

gilman = LocationInfo("Gilman", "WI", timezone="America/Chicago", latitude=45.1666, longitude=-90.8076)

stats = sun(gilman.observer, date=datetime.date.today(), tzinfo=gilman.timezone, dawn_dusk_depression=Depression.NAUTICAL)


def main(args: Namespace) -> int:

    for arg in vars(args):
        if getattr(args, arg):
            print(stats[arg].strftime("%H:%M"))

    return 0

def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(prog='sun', description='sunrise and sunset times')
    parser.add_argument('--sunrise', action='store_true')
    parser.add_argument('--sunset', action='store_true')
    parser.add_argument('--dusk', action='store_true')
    parser.add_argument('--dawn', action='store_true')

    args = parser.parse_args()
    num_args = len(sys.argv)

    if num_args != 2:
        print(f"A single command-line arg must be provided.")
        print(parser.print_usage())
        sys.exit(1)

    return args

if __name__ == "__main__":
    sys.exit(main(parse_args()))
