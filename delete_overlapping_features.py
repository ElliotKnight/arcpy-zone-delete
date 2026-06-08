import arcpy
import os
import datetime

# --- Configuration ---

# WORKFLOW OVERVIEW:
#   1. The script selects features from POLYGON_LAYER_URL using two SQL queries:
#      - POLYGON_TARGET_WHERE_CLAUSE: defines the zone where points will be deleted
#      - POLYGON_EXCLUDE_WHERE_CLAUSE: areas within that zone to protect (points here are kept)
#   2. It dissolves the target zone, then erases the exclude zone from it.
#   3. For each URL in POINT_LAYER_URLS, it finds points falling inside the result.
#   4. Dry-run mode writes those point IDs to a report file so that nothing is deleted.
#      Live mode deletes them from AGOL.
#
# RECOMMENDED WORKFLOW:
#   Step 1 — Set ENABLE_ACTUAL_DELETION = False and run the script.
#   Step 2 — Review the report file to confirm which features would be deleted.
#   Step 3 — Set ENABLE_ACTUAL_DELETION = True and run again to perform deletion.
#
#

# --- Deletion control ---
ENABLE_ACTUAL_DELETION = False  # Set to True only after reviewing the dry-run report

# --- Report output ---
REPORT_DIRECTORY = r"C:\Users\your_username\Documents"  # <-- UPDATE THIS
REPORT_FILE_PATH = os.path.join(REPORT_DIRECTORY, "Feature_Removal_Report.txt")

# --- Polygon (reference) layer ---
# The layer used to define the zone where points will be deleted.
# Can be a Feature Service URL or a local path.
POLYGON_LAYER_URL = "https://services.arcgis.com/..."  # <-- UPDATE THIS

# SQL query selecting polygons that form the deletion zone.
POLYGON_TARGET_WHERE_CLAUSE = "Status = 'Fail' OR Status = 'Automatic'"  # <-- UPDATE THIS

# SQL query selecting polygons to exclude from the deletion zone (points here are kept).
# Set to "" to skip exclusion and delete points across the entire target zone.
POLYGON_EXCLUDE_WHERE_CLAUSE = "Status = 'Pass'"  # <-- UPDATE THIS (or set to "")

# --- Point layers ---
# List of Feature Service URLs or local paths to check for deletion.
POINT_LAYER_URLS = [
    "https://services.arcgis.com/...",  # <-- UPDATE THIS
]

# --- Point attribute filter (optional) ---
# Restrict deletion to points matching specific values in a field.
# Set POINT_FILTER_VALUES = [] to check all points regardless of attribute.
POINT_FILTER_FIELD = "FIELD_NAME"  # <-- UPDATE THIS (field name to filter on)
POINT_FILTER_VALUES = []           # Example: ["VALUE1", "VALUE2"] or [] for all



# --- Helper Functions ---


def append_to_report(message):
    try:
        with open(REPORT_FILE_PATH, 'a') as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"WARNING: Could not write to report file '{REPORT_FILE_PATH}'. {e}")


def timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")



# --- Main Functions ---


def build_deletion_zone(polygon_layer_url, target_where_clause, exclude_where_clause, output_directory):

    # Builds a polygon defining where points will be deleted.

      # 1. Dissolves features matching target_where_clause  (target zone)
      # 2. Dissolves features matching exclude_where_clause (exclude zone)
      # 3. Erases exclude zone from target zone             (deletion zone)

    # Returns the path to the deletion zone shapefile, or None on failure.
    # Three intermediate shapefiles are saved to output_directory for inspection.

    print(f"\n[{timestamp()}] --- Building Deletion Zone ---")

    temp_layer = "polygon_temp_layer"
    target_path = os.path.join(output_directory, "Zone_Target_Dissolved.shp")
    exclude_path = os.path.join(output_directory, "Zone_Exclude_Dissolved.shp")
    deletion_zone_path = os.path.join(output_directory, "Zone_Deletion.shp")

    try:
        if not arcpy.Exists(polygon_layer_url):
            print(f"ERROR: Polygon layer not found or accessible: {polygon_layer_url}")
            return None

        arcpy.env.overwriteOutput = True
        arcpy.management.MakeFeatureLayer(polygon_layer_url, temp_layer)

        # Step 1: Dissolve the target zone
        print(f"Selecting target features:  {target_where_clause}")
        arcpy.management.SelectLayerByAttribute(temp_layer, "NEW_SELECTION", target_where_clause)
        target_count = int(arcpy.management.GetCount(temp_layer)[0])

        if target_count == 0:
            print("No features matched the target query. Nothing to process.")
            return None

        print(f"{target_count} target features selected. Dissolving...")
        arcpy.management.Dissolve(
            temp_layer, target_path,
            multi_part="MULTI_PART",
            unsplit_lines="DISSOLVE_LINES"
        )
        print(f"Target zone saved to: {target_path}")

        # Step 2: Dissolve the exclude zone (if a clause was provided)
        has_exclude = False
        if exclude_where_clause:
            print(f"\nSelecting exclude features: {exclude_where_clause}")
            arcpy.management.SelectLayerByAttribute(temp_layer, "NEW_SELECTION", exclude_where_clause)
            exclude_count = int(arcpy.management.GetCount(temp_layer)[0])

            if exclude_count > 0:
                print(f"{exclude_count} exclude features selected. Dissolving...")
                arcpy.management.Dissolve(
                    temp_layer, exclude_path,
                    multi_part="MULTI_PART",
                    unsplit_lines="DISSOLVE_LINES"
                )
                print(f"Exclude zone saved to: {exclude_path}")
                has_exclude = True
            else:
                print("No features matched the exclude query. Skipping exclusion step.")

        # Step 3: Erase exclude zone from target zone
        if has_exclude:
            print(f"\n[{timestamp()}] Erasing exclude zone from target zone...")
            arcpy.analysis.Erase(target_path, exclude_path, deletion_zone_path)
            print(f"Deletion zone saved to: {deletion_zone_path}")
            return deletion_zone_path
        else:
            print("No exclusion applied. Using target zone as the deletion zone.")
            return target_path

    except arcpy.ExecuteError:
        print(f"\nArcGIS error building deletion zone:\n{arcpy.GetMessages(2)}")
        return None
    except Exception as e:
        print(f"\nUnexpected error building deletion zone: {e}")
        return None
    finally:
        if arcpy.Exists(temp_layer):
            arcpy.management.Delete(temp_layer)


def process_point_layer(point_layer_url, deletion_zone_path, filter_field, filter_values, perform_deletion):

    #  Finds points within the deletion zone (optionally filtered by attribute) and
    #  either deletes them or logs their IDs to the report file.

    layer_name = None
    print(f"\n[{timestamp()}] Checking: {point_layer_url}")

    try:
        if not arcpy.Exists(point_layer_url):
            print(f"ERROR: Layer not found or accessible: {point_layer_url}. Skipping.")
            return
        if not arcpy.Exists(deletion_zone_path):
            print(f"ERROR: Deletion zone '{deletion_zone_path}' not found. Skipping.")
            return

        arcpy.env.overwriteOutput = True
        layer_name = arcpy.CreateUniqueName(
            "points_layer",
            arcpy.env.scratchWorkspace or "in_memory"
        )
        arcpy.management.MakeFeatureLayer(point_layer_url, layer_name)

        # Attribute filter
        if filter_values:
            where_clause = " OR ".join([f"{filter_field} = '{v}'" for v in filter_values])
            print(f"Attribute filter: {where_clause}")
            arcpy.management.SelectLayerByAttribute(layer_name, "NEW_SELECTION", where_clause)
            spatial_selection_type = "SUBSET_SELECTION"
        else:
            arcpy.management.SelectLayerByAttribute(layer_name, "NEW_SELECTION")
            spatial_selection_type = "NEW_SELECTION"

        candidate_count = int(arcpy.management.GetCount(layer_name)[0])
        if candidate_count == 0:
            print("No features match the attribute filter. Skipping.")
            return

        print(f"{candidate_count} candidate features to check spatially.")

        # Spatial filter
        arcpy.management.SelectLayerByLocation(
            in_layer=layer_name,
            overlap_type="COMPLETELY_WITHIN",
            select_features=deletion_zone_path,
            selection_type=spatial_selection_type
        )

        match_count = int(arcpy.management.GetCount(layer_name)[0])

        if match_count == 0:
            print("No features fall within the deletion zone.")
            return

        print(f"{match_count} features found within the deletion zone.")

        if perform_deletion:
            print(f"DELETING {match_count} features...")
            arcpy.management.DeleteFeatures(layer_name)
            print(f"[{timestamp()}] Deletion complete.")
            append_to_report(f"\nDELETED: {match_count} features from:\n{point_layer_url}")
        else:
            print(f"DRY RUN: {match_count} features would be deleted. Writing IDs to report.")

            oid_field = next(
                (f.name for f in arcpy.ListFields(layer_name) if f.type == 'OID'),
                'OBJECTID'
            )

            append_to_report(f"\n{'-' * 60}")
            append_to_report(f"DRY RUN — {match_count} features would be deleted from:")
            append_to_report(point_layer_url)
            append_to_report(f"OID Field: {oid_field}")

            ids = []
            with arcpy.da.SearchCursor(layer_name, [oid_field]) as cursor:
                for row in cursor:
                    ids.append(str(row[0]))

            append_to_report("\n".join(ids) if ids else "ERROR: No IDs retrieved.")
            print(f"IDs written to: {REPORT_FILE_PATH}")

    except arcpy.ExecuteError:
        print(f"\nArcGIS error processing {point_layer_url}:\n{arcpy.GetMessages(2)}")
    except Exception as e:
        print(f"\nUnexpected error processing {point_layer_url}: {e}")
    finally:
        if layer_name and arcpy.Exists(layer_name):
            arcpy.management.Delete(layer_name)


# --- Execution ---


if __name__ == "__main__":

    start_time = datetime.datetime.now()
    mode_label = "LIVE DELETION" if ENABLE_ACTUAL_DELETION else "DRY RUN (no changes will be made)"

    print("=" * 80)
    print("AGOL FEATURE DELETION SCRIPT")
    print(f"Started : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode    : {mode_label}")
    print("=" * 80)

    # Validate report directory
    try:
        os.makedirs(REPORT_DIRECTORY, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Could not create report directory '{REPORT_DIRECTORY}': {e}")
        exit(1)

    # Initialise report file
    try:
        with open(REPORT_FILE_PATH, 'w') as f:
            f.write("FEATURE REMOVAL REPORT\n")
            f.write(f"Started : {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode    : {mode_label}\n")
            f.write("=" * 80 + "\n")
    except Exception as e:
        print(f"ERROR: Could not create report file at '{REPORT_FILE_PATH}': {e}")
        exit(1)

    arcpy.env.overwriteOutput = True

    try:
        # Step 1: Build the deletion zone from the polygon layer
        deletion_zone = build_deletion_zone(
            polygon_layer_url=POLYGON_LAYER_URL,
            target_where_clause=POLYGON_TARGET_WHERE_CLAUSE,
            exclude_where_clause=POLYGON_EXCLUDE_WHERE_CLAUSE,
            output_directory=REPORT_DIRECTORY
        )

        if not deletion_zone:
            print("\nNo deletion zone was created. Stopping.")
            append_to_report("\nNo deletion zone created. No features processed.")
        else:
            # Step 2: Check each point layer against the deletion zone
            total = len(POINT_LAYER_URLS)
            print(f"\n[{timestamp()}] Processing {total} point layer(s)...")
            append_to_report(f"\nProcessing {total} point layer(s).")

            for i, url in enumerate(POINT_LAYER_URLS, start=1):
                print(f"\n{'=' * 30} Layer {i}/{total} {'=' * 30}")
                process_point_layer(
                    point_layer_url=url,
                    deletion_zone_path=deletion_zone,
                    filter_field=POINT_FILTER_FIELD,
                    filter_values=POINT_FILTER_VALUES,
                    perform_deletion=ENABLE_ACTUAL_DELETION
                )

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        append_to_report(f"\nCRITICAL ERROR: {e}")

    end_time = datetime.datetime.now()
    duration = end_time - start_time
    summary = (
        f"\n{'=' * 80}\n"
        f"Finished : {end_time.strftime('%Y-%m-%d %H:%M:%S')} | Duration: {duration}\n"
    )

    print(summary)
    print(f"Report saved to: {REPORT_FILE_PATH}")
    append_to_report(summary)
