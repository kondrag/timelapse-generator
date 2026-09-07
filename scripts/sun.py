#!/bin/env python

import argparse
import datetime
import sys

from argparse import Namespace
from astral import Depression, LocationInfo
from astral.sun import sun

gilman = LocationInfo("Gilman", "WI", timezone="America/Chicago", latitude=45.1666, longitude=-90.8076)


def stats_for(date: datetime.date) -> dict:
    return sun(gilman.observer, date=date, tzinfo=gilman.timezone, dawn_dusk_depression=Depression.NAUTICAL)


def main(args: Namespace) -> int:

    stats = stats_for(args.date)
    for arg in vars(args):
        if arg in ("sunrise", "sunset", "dusk", "dawn") and getattr(args, arg):
            print(stats[arg].strftime("%H:%M"))

    return 0

def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(prog='sun', description='sunrise and sunset times')
    parser.add_argument('--sunrise', action='store_true')
    parser.add_argument('--sunset', action='store_true')
    parser.add_argument('--dusk', action='store_true')
    parser.add_argument('--dawn', action='store_true')
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today(),
                        help='date to compute for (default: today), YYYY-MM-DD')

    args = parser.parse_args()

    position_flags = [flag for flag in ("sunrise", "sunset", "dusk", "dawn") if getattr(args, flag)]
    if len(position_flags) != 1:
        print(f"A single position flag must be provided (got {len(position_flags)}).")
        print(parser.print_usage())
        sys.exit(1)

    return args

if __name__ == "__main__":
    sys.exit(main(parse_args()))
