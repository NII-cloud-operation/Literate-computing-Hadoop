import csv
import pandas as pd
import os

def get_row(header, machines):
    return [machines[h] for h in header]

def read_machines(path):
    header = None
    machines = []
    with open(path, 'rb') as f:
        for row in csv.reader(f):
            if not header:
                header = row
            elif len(row) > 2 and len(row[0]) > 0 and len(row[1]) > 0:
                m = dict(zip(header, row))
                for col in header[5:10]:
                    m[col] = int(m[col].strip()) if m[col].strip() != '-' else None
                for col in header[10:]:
                    m[col] = (len(m[col].strip()) > 0)
                machines.append(m)
    return (header, machines)
