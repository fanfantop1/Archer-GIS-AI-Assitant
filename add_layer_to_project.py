try:
    import arcpy
except ModuleNotFoundError:
    import arcpy_stub as arcpy
import sys
import os
import time

def add_layer(project_path, map_name, layer_path):
    """Adds a layer to a specific map in an ArcGIS Pro project."""
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5

    if not os.path.exists(project_path):
        print(f"Error: Project file not found at {project_path}")
        return False # Indicate failure
    if not os.path.exists(layer_path):
         print(f"Error: Layer file not found at {layer_path}")
         return False # Indicate failure

    aprx = None # Initialize aprx to None
    for attempt in range(MAX_RETRIES):
        try:
            print(f"Attempt {attempt + 1}/{MAX_RETRIES}: Opening project: {project_path}")
            aprx = arcpy.mp.ArcGISProject(project_path)

            print(f"Looking for map: {map_name}")
            # Use listMaps without wildcard first for exact match
            maps = aprx.listMaps(map_name)
            if not maps:
                 # If exact match fails, try wildcard (useful if name isn't precise)
                 print(f"Exact map name '{map_name}' not found, trying wildcard search...")
                 maps = aprx.listMaps(f"*{map_name}*") # Example wildcard search
                 if not maps:
                     print(f"Error: Map like '{map_name}' not found in the project.")
                     print("Available maps:", [m.name for m in aprx.listMaps()])
                     return False # Indicate failure

            target_map = maps[0] # Use the first map found
            print(f"Found map: {target_map.name}")

            print(f"Adding layer: {layer_path} to map: {target_map.name}")
            # Check if layer already exists to avoid duplicates (optional but good practice)
            existing_layers = [lyr.name for lyr in target_map.listLayers() if lyr.dataSource == layer_path]
            if existing_layers:
                print(f"Layer with data source '{layer_path}' already exists in map '{target_map.name}'. Skipping add.")
                return True # Indicate success (layer is present)

            target_map.addDataFromPath(layer_path)
            print("Layer added.")

            print("Saving project...")
            aprx.save()
            print("Project saved successfully.")
            return True # Indicate success

        except arcpy.ExecuteError as e:
            # Specific handling for potential locking errors (Error 000464)
            if "000464" in str(e):
                 print(f"Warning: Project file '{project_path}' may be locked (Error 000464). Retrying in {RETRY_DELAY_SECONDS} seconds...")
                 time.sleep(RETRY_DELAY_SECONDS)
                 continue # Go to the next retry attempt
            else:
                 print(f"An arcpy error occurred: {e}")
                 return False # Indicate failure for other arcpy errors
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            # Consider logging the full traceback here for debugging
            # import traceback
            # print(traceback.format_exc())
            return False # Indicate failure
        finally:
            # Ensure the project object is deleted to release potential locks
            if aprx:
                del aprx
                print("ArcGISProject object released.")

    print(f"Error: Failed to add layer after {MAX_RETRIES} attempts.")
    return False # Indicate failure after all retries

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python add_layer_to_project.py <path_to_aprx> <map_name> <path_to_layer>")
        sys.exit(1) # Exit with error code 1 for incorrect usage

    project_file = sys.argv[1]
    map_to_update = sys.argv[2]
    layer_to_add = sys.argv[3]

    success = add_layer(project_file, map_to_update, layer_to_add)

    if success:
        sys.exit(0) # Exit with success code 0
    else:
        sys.exit(2) # Exit with error code 2 for processing failure