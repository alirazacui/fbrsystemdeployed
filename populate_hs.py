import os, json, sys
import django

# Setup Django env
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from pos.models import HSCode

json_file = '/home/ali-raza/fbr_pos_project/fbr_pos_frontend/src/assets/hs_codes.json'
with open(json_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Loaded {len(data)} items from JSON.")

# Clear existing
HSCode.objects.all().delete()

# Bulk create
objects = []
seen = set()
for item in data:
    if item['code'] not in seen:
        seen.add(item['code'])
        objects.append(HSCode(code=item['code'], description=item['description']))

batch_size = 1000
for i in range(0, len(objects), batch_size):
    batch = objects[i:i+batch_size]
    HSCode.objects.bulk_create(batch)
    print(f"Inserted batch {i//batch_size + 1}")

print("Done populating HSCodes.")
