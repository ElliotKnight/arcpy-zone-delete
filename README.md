# arcpy-zone-delete

A Python script that deletes point features from AGOL Feature Services if they fall inside a polygon zone. Designed to be run from the Python terminal in ArcGIS Pro.

It has a dry run mode that shows you what would be deleted before anything actually happens. Always do a dry run first.

# Requirements

- ArcGIS Pro (for arcpy)
- Signed in to an AGOL account with edit access to the Feature Services you want to modify

# How it works

The script takes a polygon layer and two SQL queries — one to define the zone where points should be deleted, and one to define areas within that zone that should be left alone. It dissolves and erases those together, then checks each of your point layers against the result.

It saves three shapefiles to your report directory so you can inspect the zones in ArcGIS Pro before committing to a deletion.

##Setup

Open `delete_overlapping_features.py` and fill in the values at the top of the file. Everything that needs updating is marked with `# <-- UPDATE THIS`.

The main things to set are:

- `REPORT_DIRECTORY` — where the report file and intermediate shapefiles will be saved
- `POLYGON_LAYER_URL` — the polygon Feature Service that defines your zones
- `POLYGON_TARGET_WHERE_CLAUSE` — SQL query for the polygons you want to delete points within
- `POLYGON_EXCLUDE_WHERE_CLAUSE` — SQL query for areas to protect (set to `""` to skip)
- `POINT_LAYER_URLS` — list of point Feature Services to check
- `POINT_FILTER_VALUES` — optionally restrict to points matching certain attribute values (leave as `[]` for all points)

# Running the script

Open the Python terminal in ArcGIS Pro (Analysis > Python) and run:

```python
exec(open(r"C:\path\to\delete_overlapping_features.py").read())
```

Or open it in the ArcGIS Pro editor and click Run.

# Recommended workflow

1. Set `ENABLE_ACTUAL_DELETION = False` and run the script
2. Check the report file in `REPORT_DIRECTORY` — it lists the Object IDs of every feature that would be deleted
3. Load the shapefiles into ArcGIS Pro if you want to visually check the deletion zone
4. When you're happy, set `ENABLE_ACTUAL_DELETION = True` and run again
