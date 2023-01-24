 #!/usr/bin/env python3

import csv
import json

mapping_entries = []
repositories = []

with open('repomap.csv') as csvfile:
    reporeader = csv.reader(csvfile)
    for row in reporeader:
        if len(row) == 9:  # the others are useless
            map_found = False
            for entry in mapping_entries:
                if entry['source'] == row[0]:
                    map_found = True
                    if row[2] not in entry['target']:
                        entry['target'].append(row[2])
            if not map_found:
                mapping_entries.append({'source': row[0], 'target': [row[2]]})

            repo7_found = False
            repo7_entry = {'major_version': '7', 'repoid': row[0], 'arch': row[5], 'channel': row[7], 'repo_type': row[6]}
            for repo in repositories:
                if repo['pesid'] == row[0]:
                    repo7_found = True
                    repo['entries'].append(repo7_entry)
            if not repo7_found:
                repositories.append({'pesid': row[0], 'entries': [repo7_entry]})

            repo8_found = False
            repo8_entry = {'major_version': '8', 'repoid': row[1], 'arch': row[5], 'channel': row[8], 'repo_type': row[6]}
            for repo in repositories:
                if repo['pesid'] == row[2]:
                    repo8_found = True
                    repo['entries'].append(repo8_entry)
            if not repo8_found:
                repositories.append({'pesid': row[2], 'entries': [repo8_entry]})


for repo in repositories:
    repo['entries'] = [dict(s) for s in set(frozenset(d.items()) for d in repo['entries'])]

mapping = [{"source_major_version": "7", "target_major_version": "8", "entries": mapping_entries}]
repomap = {'datetime': '202204020934Z', 'version_format': '1.0.0', 'mapping': mapping, 'repositories': repositories}
print(json.dumps(repomap, indent=4))
