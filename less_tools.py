from langchain.tools import tool
try:
    import arcpy
except ModuleNotFoundError:
    import arcpy_stub as arcpy
import os
from typing import List, Dict, Any, Literal, Union, Optional
import json
import time
import aiohttp
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
import requests
from urllib.parse import urlparse
import fiona
import rasterio
import traceback
import tarfile
import re
from arcgis.gis import GIS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

ARCGIS_URL = "https://www.arcgis.com"
ARC_USER = os.environ.get("ARC_USER")
ARC_PASS = os.environ.get("ARC_PASS")


arcpy.env.overwriteOutput = True


# Helper Functions
def _feature_class_exists(feature_class: str) -> bool:
    """Checks if a feature class exists."""
    try:
        return arcpy.Exists(feature_class)
    except Exception:
        return False

def _dataset_exists(dataset: str) -> bool:
    """Checks if any dataset (feature class, table, raster, etc.) exists."""
    try:
        return arcpy.Exists(dataset)
    except Exception:
        return False

def _is_valid_field_name(feature_class: str, field_name: str) -> bool:
    """Checks if a field name is valid for a given feature class."""
    if not _feature_class_exists(feature_class):
        return False
    try:
        fields = arcpy.ListFields(feature_class)
        # Make case-insensitive comparison
        field_name_lower = field_name.lower() if field_name else ""
        return any(field.name.lower() == field_name_lower for field in fields)
    except Exception:
        return False

def _validate_raster_exists(raster_path: str) -> bool:
    """Validates that a raster exists and is accessible.
    
    Args:
        raster_path: Path to the raster to validate
        
    Returns:
        bool: True if the raster exists and is accessible, False otherwise
    """
    try:
        if not arcpy.Exists(raster_path):
            return False
        # Try to create a raster object to ensure it's a valid raster
        raster = arcpy.Raster(raster_path)
        return True
    except Exception:
        return False
    
def get_gis_connection() -> Optional[GIS]:
    """
    Helper function to establish GIS connection.
    Handles authentication securely using username/password from environment variables.
    Returns an anonymous connection if authentication fails or credentials are not set.
    """
    if ARC_USER and ARC_PASS:
        try:
            print(f"Attempting to connect to {ARCGIS_URL} as user {ARC_USER}...")
            gis = GIS(ARCGIS_URL, username=ARC_USER, password=ARC_PASS)
            # Optionally, check if the connection is valid by accessing user profile
            print(f"Successfully connected to {gis.url} as user {gis.properties.user.username}")
            return gis
        except Exception as e:
            print(f"Error connecting to ArcGIS with username/password: {e}")
            print("Falling back to anonymous connection. Functionality may be limited.")
            gis = GIS(ARCGIS_URL)
            return gis
    else:
        print("Warning: ARC_USER or ARC_PASS environment variable not set.")
        print("Attempting anonymous connection. Functionality may be limited.")
        try:
            gis = GIS(ARCGIS_URL)
            print(f"Successfully established anonymous connection to {gis.url}")
            return gis
        except Exception as e:
            print(f"Error establishing anonymous connection to ArcGIS: {e}")
            return None

    

# Feature Class Tools
@tool
def buffer_features(input_features: str, output_features: str, buffer_distance: float, buffer_unit: str) -> str:
    """Creates buffer polygons around input features at a specified distance.
    
    This tool generates buffer polygons around input points, lines, or polygons. Buffers can be 
    used for proximity analysis, creating protection zones, or visual enhancement of features.
    The buffer distance determines how far from each feature the buffer extends.
    The dataset need not be in a projected coordinate system for the buffer distance to be set in meters, km, etc.
    
    GIS Concepts:
    - Buffers create new polygon features that represent areas within a specified distance of input features
    - Positive buffer distances create larger polygons around the inputs
    - Buffer unit determines the measurement units (e.g., meters, feet)
    - Useful for answering questions like "What's within X distance of this feature?"

    Args:
        input_features: The path to the input feature class (points, lines, or polygons).
                       Must be an existing feature class in a workspace.
        output_features: The path where the buffered feature class will be saved.
                        Will be overwritten if it already exists.
        buffer_distance: The distance to buffer around each feature.
                        Must be a positive number.
        buffer_unit: The unit of measurement for the buffer distance.
                    Valid values: 'Meters', 'Feet', 'Kilometers', 'Miles', 'NauticalMiles', or 'Yards'.

    Returns:
        A message indicating success or failure with details about the operation.
        
    Example:
        >>> buffer_features("D:/data/cities.shp", "D:/output/cities_buffer.shp", 1000, "Meters")
        "Successfully buffered D:/data/cities.shp to D:/output/cities_buffer.shp."
        
    Notes:
        - The input feature class must exist
        - The output will be overwritten if it already exists
        - The spatial reference of the output will match the input
    """
    try:
        if not arcpy.Exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."
        if not isinstance(buffer_distance, (int, float)):
            return "Error: buffer_distance must be a number."
            
        # Make buffer_unit case insensitive by converting to lowercase for comparison
        # but preserve the original case for use in the arcpy command
        valid_units = ['meters', 'feet', 'kilometers', 'miles', 'nauticalmiles', 'yards']
        if buffer_unit.lower() not in valid_units:
            return "Error: Invalid buffer_unit. Must be 'Meters', 'Feet', 'Kilometers', 'Miles', 'NauticalMiles', or 'Yards'."

        # Use the original case provided by the user, since it passed validation
        arcpy.analysis.Buffer(input_features, output_features, f"{buffer_distance} {buffer_unit}")
        return f"Successfully buffered {input_features} to {output_features}."
    except arcpy.ExecuteError:
        return f"Error buffering features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def clip_features(input_features: str, clip_features: str, output_features: str) -> str:
    """Clips the input features using the clip features.

    Args:
        input_features: The path to the input feature class to be clipped.
        clip_features: The path to the feature class used to clip the input features.
        output_features: The path to the output (clipped) feature class.
    """
    try:
        if not _feature_class_exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."
        if not _feature_class_exists(clip_features):
            return f"Error: Clip feature class '{clip_features}' does not exist."
        arcpy.analysis.Clip(input_features, clip_features, output_features)
        return f"Successfully clipped '{input_features}' with '{clip_features}' to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error clipping features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def dissolve_features(input_features: str, output_features: str, dissolve_field: str = "", 
                     statistics_fields: str = "", multi_part: str = "MULTI_PART") -> str:
    """Dissolves features based on specified attributes.

    Args:
        input_features: The path to the input feature class.
        output_features: The path to the output feature class.
        dissolve_field: The field(s) to dissolve on (optional, comma-separated).
        statistics_fields: Fields to calculate statistics on (optional, format: "field_name SUM;field_name MEAN").
        multi_part: Whether to create multi-part features ("MULTI_PART" or "SINGLE_PART").
    """
    try:
        if not _feature_class_exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."

        if multi_part.upper() not in ("MULTI_PART", "SINGLE_PART"):
            return "Error: Invalid value for 'multi_part'. Must be 'MULTI_PART' or 'SINGLE_PART'."

        arcpy.management.Dissolve(input_features, output_features, dissolve_field, statistics_fields, multi_part)
        return f"Successfully dissolved features from '{input_features}' to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error dissolving features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def merge_features(input_features: List[str], output_features: str) -> str:
    """Merges multiple feature classes into a single feature class.

    Args:
        input_features: A list of paths to the input feature classes.
        output_features: The path to the output feature class.
    """
    try:
        for fc in input_features:
            if not _feature_class_exists(fc):
                return f"Error: Input feature class '{fc}' does not exist."
        arcpy.management.Merge(input_features, output_features)
        return f"Successfully merged features into '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error merging features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def append_features(input_features: List[str], target_features: str, schema_type: str = "NO_TEST") -> str:
    """Appends features from one or more feature classes to an existing target feature class.

    Args:
        input_features: A list of paths to the input feature classes.
        target_features: The path to the existing target feature class.
        schema_type: How to handle schema differences ("TEST", "NO_TEST"). Default: "NO_TEST".
    """
    try:
        for fc in input_features:
            if not _feature_class_exists(fc):
                return f"Error: Input feature class '{fc}' does not exist."
        if not _feature_class_exists(target_features):
            return f"Error: Target feature class '{target_features}' does not exist."

        if schema_type.upper() not in ("TEST", "NO_TEST"):
            return "Error: Invalid value for 'schema_type'. Must be 'TEST' or 'NO_TEST'."

        arcpy.management.Append(input_features, target_features, schema_type)
        return f"Successfully appended features to '{target_features}'."
    except arcpy.ExecuteError:
        return f"Error appending features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def delete_features(input_features: str) -> str:
    """Deletes a feature class or table.

    Args:
        input_features: The path to the feature class or table to delete.
    """
    try:
        if not _dataset_exists(input_features):
            return f"Error: Input dataset '{input_features}' does not exist."
        arcpy.management.Delete(input_features)
        return f"Successfully deleted '{input_features}'."
    except arcpy.ExecuteError:
        return f"Error deleting features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def create_feature_class(out_path: str, out_name: str, geometry_type: str, template: str = "", spatial_reference: str = "") -> str:
    """Creates a new feature class.

    Args:
        out_path: The path to the geodatabase or folder where the feature class will be created.
        out_name: The name of the new feature class.
        geometry_type: The geometry type (e.g., "POLYGON", "POINT", "POLYLINE").
        template: An optional template feature class (for schema).
        spatial_reference: An optional spatial reference (e.g., "WGS 1984").
    """
    try:
        if not arcpy.Exists(out_path):
            return f"Error: Output path '{out_path}' does not exist."
        if geometry_type.upper() not in ("POINT", "MULTIPOINT", "POLYGON", "POLYLINE", "MULTIPATCH"):
            return "Error: Invalid geometry_type. Must be 'POINT', 'MULTIPOINT', 'POLYGON', 'POLYLINE', or 'MULTIPATCH'."
        if template and not _feature_class_exists(template):
            return f"Error: Template feature class '{template}' does not exist."

        if spatial_reference:
            try:
                sr = arcpy.SpatialReference(spatial_reference)
            except:
                return f"Error: Invalid spatial reference '{spatial_reference}'."
        else:
            sr = None

        arcpy.management.CreateFeatureclass(out_path, out_name, geometry_type.upper(), template, spatial_reference=sr)
        return f"Successfully created feature class '{out_name}' in '{out_path}'."
    except arcpy.ExecuteError:
        return f"Error creating feature class: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def add_field(in_table: str, field_name: str, field_type: str, field_length: int = None, 
              field_precision: int = None, field_scale: int = None) -> str:
    """Adds a new field to a feature class or table.
    Ensure that you give the length, precision, and scale only if the field type requires it.
    If the field type is TEXT, provide the field_length.
    If the field type is FLOAT or DOUBLE, provide field_precision and field_scale.

    Args:
        in_table: The path to the feature class or table.
        field_name: The name of the new field.
        field_type: The type of the field (TEXT, SHORT, LONG, FLOAT, DOUBLE, DATE, BLOB, RASTER, GUID).
        field_length: The length of the field (for text fields).
        field_precision: The precision of the field (for numeric fields).
        field_scale: The scale of the field (for numeric fields).
    """
    try:
        if not _dataset_exists(in_table):
            return f"Error: Input table/feature class '{in_table}' does not exist."
        if _is_valid_field_name(in_table, field_name):
            return f"Error: Field '{field_name}' already exists in '{in_table}'."

        # Use case-insensitive validation for field_type
        valid_types = ["TEXT", "SHORT", "LONG", "FLOAT", "DOUBLE", "DATE", "BLOB", "RASTER", "GUID"]
        if field_type.upper() not in [t.upper() for t in valid_types]:
            return f"Error: Invalid field_type. Must be one of: {', '.join(valid_types)}"

        # Always use uppercase for field_type to ensure consistency
        arcpy.management.AddField(in_table, field_name, field_type.upper(), field_precision, field_scale, field_length)
        return f"Successfully added field '{field_name}' to '{in_table}'."
    except arcpy.ExecuteError:
        return f"Error adding field: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def calculate_field(in_table: str, field_name: str, expression: str, expression_type: str = "PYTHON3") -> str:
    """Calculates values for a field in a feature class or table.

    Args:
        in_table: The path to the feature class or table.
        field_name: The name of the field to calculate.
        expression: The expression to use for calculation.
        expression_type: The type of expression ("PYTHON3", "ARCADE", "SQL"). Default: "PYTHON3".
    """
    try:
        if not _dataset_exists(in_table):
            return f"Error: Input table/feature class '{in_table}' does not exist."
        if not _is_valid_field_name(in_table, field_name):
            return f"Error: Field '{field_name}' does not exist in '{in_table}'."

        # Use case-insensitive validation by converting to upper case
        valid_types = ["PYTHON3", "ARCADE", "SQL"]
        if expression_type.upper() not in [t.upper() for t in valid_types]:
            return f"Error: Invalid expression_type. Must be one of: {', '.join(valid_types)}"

        # Use the original case for 'PYTHON3' or convert other values to uppercase for consistency
        if expression_type.upper() == 'PYTHON3':
            expr_type = 'PYTHON3'  # Use standard case for Python
        else:
            expr_type = expression_type.upper()  # Use uppercase for other types
            
        arcpy.management.CalculateField(in_table, field_name, expression, expr_type)
        return f"Successfully calculated field '{field_name}' in '{in_table}'."
    except arcpy.ExecuteError:
        return f"Error calculating field: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def select_features(input_features: str, output_features: str, where_clause: str) -> str:
    """Selects features by attribute and saves them to a new feature class. Uses case-insensitive comparisons for string fields.
    Use the field name not the alias name to make the query.

    Args:
        input_features: The path to the input feature class.
        output_features: The path to the output feature class.
        where_clause: The SQL WHERE clause to select features.
    """
    try:
        if not arcpy.Exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."

        modified_clause = where_clause

        # Helper to get field type
        def get_field_type(field_name):
            fields = arcpy.ListFields(input_features, field_name)
            return fields[0].type if fields else None

        # Patterns to find field = 'value' or field = "value" with any operator
        patterns = [
            r"(\w+)\s*(=|\bLIKE\b)\s*'([^']*)'",  # Single quotes
            r'(\w+)\s*(=|\bLIKE\b)\s*"([^"]*)"'   # Double quotes
        ]

        for pattern in patterns:
            matches = re.findall(pattern, modified_clause, flags=re.IGNORECASE)
            for match in matches:
                field, operator, value = match
                field_type = get_field_type(field)
                if field_type == 'String':
                    # Apply UPPER() to make comparison case-insensitive
                    old = f"{field} {operator} '{value}'" if "'" in pattern else f'{field} {operator} "{value}"'
                    new = f"UPPER({field}) {operator} UPPER('{value}')" if "'" in pattern else f'UPPER({field}) {operator} UPPER("{value}")'
                    modified_clause = modified_clause.replace(old, new)
                    print(f"Adjusted clause for string field '{field}': {old} -> {new}")

        # Execute Select with modified clause
        if modified_clause != where_clause:
            print(f"Modified WHERE clause to: {modified_clause}")

        arcpy.analysis.Select(input_features, output_features, modified_clause)
        return f"Successfully created '{output_features}' using case-insensitive WHERE clause."
    
    except arcpy.ExecuteError:
        # Fallback to original clause if modified fails
        try:
            arcpy.analysis.Select(input_features, output_features, where_clause)
            return f"Successfully created '{output_features}' using original WHERE clause."
        except:
            return f"Error: {arcpy.GetMessages(2)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

@tool
def project_features(input_features: str, output_features: str, out_coor_system: str) -> str:
    """Projects a feature class to a new coordinate system.

    Args:
        input_features: The path to the input feature class.
        output_features: The path to the output feature class.
        out_coor_system: The output coordinate system (e.g., a WKID, name, or path to a .prj file).
    """
    try:
        if not _feature_class_exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."
        try:
            sr = arcpy.SpatialReference(out_coor_system)
        except:
            return f"Error: Invalid output coordinate system '{out_coor_system}'."

        arcpy.management.Project(input_features, output_features, sr)
        return f"Successfully projected '{input_features}' to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error projecting features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"



@tool
def intersect_features(input_features: List[str], output_features: str, join_attributes: str = "ALL") -> str:
    """Computes the geometric intersection of multiple feature classes.

    Args:
        input_features: A list of paths to the input feature classes.
        output_features: The path to the output feature class.
        join_attributes: Which attributes to join ("ALL", "NO_FID", "ONLY_FID"). Default "ALL".
    """
    try:
        for fc in input_features:
            if not _feature_class_exists(fc):
                return f"Error: Input feature class '{fc}' does not exist."
        if join_attributes.upper() not in ("ALL", "NO_FID", "ONLY_FID"):
            return "Error: Invalid value for join_attributes. Must be 'ALL', 'NO_FID' or 'ONLY_FID'."
        arcpy.analysis.Intersect(input_features, output_features, join_attributes)
        return f"Successfully intersected features to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error intersecting features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def union_features(input_features: List[str], output_features: str) -> str:
    """Computes the geometric union of multiple feature classes.

    Args:
        input_features: A list of paths to the input feature classes.
        output_features: The path to the output feature class.
    """
    try:
        for fc in input_features:
            if not _feature_class_exists(fc):
                return f"Error: Input feature class '{fc}' does not exist."
        arcpy.analysis.Union(input_features, output_features)
        return f"Successfully unioned features to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error unioning features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def erase_features(input_features: str, erase_features: str, output_features: str) -> str:
    """Erases parts of the input features that overlap with the erase features.

    Args:
        input_features: The path to the input feature class.
        erase_features: The path to the feature class used to erase from the input.
        output_features: The path to the output feature class.
    """
    try:
        if not _feature_class_exists(input_features):
            return f"Error: Input feature class '{input_features}' does not exist."
        if not _feature_class_exists(erase_features):
            return f"Error: Erase feature class '{erase_features}' does not exist."
        arcpy.analysis.Erase(input_features, erase_features, output_features)
        return f"Successfully erased features from '{input_features}' to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error erasing features: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def spatial_join(target_features: str, join_features: str, output_features: str, 
                join_operation: str = "JOIN_ONE_TO_ONE", join_type: str = "KEEP_ALL", 
                match_option: str = "INTERSECT") -> str:
    """Performs a spatial join between two feature classes.

    Args:
        target_features: The path to the target feature class.
        join_features: The path to the join feature class.
        output_features: The path to the output feature class.
        join_operation: The join operation ("JOIN_ONE_TO_ONE" or "JOIN_ONE_TO_MANY").
        join_type: The join type ("KEEP_ALL" or "KEEP_COMMON").
        match_option: The spatial match option (e.g., "INTERSECT", "WITHIN_A_DISTANCE", "CONTAINS").
    """
    try:
        if not _feature_class_exists(target_features):
            return f"Error: Target feature class '{target_features}' does not exist."
        if not _feature_class_exists(join_features):
            return f"Error: Join feature class '{join_features}' does not exist."

        if join_operation.upper() not in ("JOIN_ONE_TO_ONE", "JOIN_ONE_TO_MANY"):
            return "Error: Invalid 'join_operation'. Must be 'JOIN_ONE_TO_ONE' or 'JOIN_ONE_TO_MANY'."
        if join_type.upper() not in ("KEEP_ALL", "KEEP_COMMON"):
            return "Error: Invalid 'join_type'. Must be 'KEEP_ALL' or 'KEEP_COMMON'."

        arcpy.analysis.SpatialJoin(target_features, join_features, output_features, 
                                 join_operation, join_type, match_option=match_option)
        return f"Successfully performed spatial join to '{output_features}'."
    except arcpy.ExecuteError:
        return f"Error performing spatial join: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


@tool
def zonal_statistics_as_table(
    in_zone_data: str,
    zone_field: str,
    in_value_raster: str,
    out_table: str,
    statistics_type: Union[str, List[str]] = "MEAN",
    ignore_nodata: Literal['DATA', 'NODATA', '#'] | None = "#",
    process_as_multidimensional: Literal['CURRENT_SLICE', 'ALL_SLICES', '#'] | None = "#",
    percentile_values: str = "#",
    percentile_interpolation_type: Literal['AUTO_DETECT', 'NEAREST', 'LINEAR', '#'] | None = "#",
    circular_calculation: Literal['ARITHMETIC', 'CIRCULAR', '#'] | None = "#",
    circular_wrap_value: str = "#",
    out_join_layer: str = "#"
) -> str:
    """
    A robust wrapper for arcpy.sa.ZonalStatisticsAsTable that supports either a single statistic,
    "ALL", or a list of specific statistics, merging the results into a single output table.

    Args:
        in_zone_data (str): Dataset defining zones (feature class or raster).
        zone_field (str): Field in the zone dataset defining zones.
        in_value_raster (str): Raster for which statistics are calculated.
        out_table (str): Output table path.
        statistics_type (str or List[str]): Statistic(s) to calculate. Valid options are:
                                             ("ALL", "MEAN", "MAJORITY", "MAJORITY_COUNT", "MAJORITY_PERCENT", "MAXIMUM", "MEDIAN",
                                             "MINIMUM", "MINORITY", "MINORITY_COUNT", "MINORITY_PERCENT", "PERCENTILE", "RANGE", "STD",
                                             "SUM", "VARIETY", "MIN_MAX", "MEAN_STD", "MIN_MAX_MEAN", "MAJORITY_VALUE_COUNT_PERCENT",
                                             "MINORITY_VALUE_COUNT_PERCENT")
        ignore_nodata (str): 'DATA', 'NODATA', or '#' (default).
        process_as_multidimensional (str): 'CURRENT_SLICE', 'ALL_SLICES', or '#' (default).
        percentile_values (str): Percentile value(s) if statistics_type is 'PERCENTILE' (default "#").
        percentile_interpolation_type (str): 'AUTO_DETECT', 'NEAREST', 'LINEAR', or '#' (default).
        circular_calculation (str): 'ARITHMETIC', 'CIRCULAR', or '#' (default).
        circular_wrap_value (str): Wrap value for circular calculations (default "#").
        out_join_layer (str): Optional output join layer (default "#").

    Returns:
        str: Success message if the tool runs successfully, or an error message.
    """
    try:
        # Validate input datasets and zone field.
        if not _dataset_exists(in_zone_data):
            return f"Error: Input zone dataset '{in_zone_data}' does not exist."
        if not _dataset_exists(in_value_raster):
            return f"Error: Input value raster '{in_value_raster}' does not exist."
        if not _is_valid_field_name(in_zone_data, zone_field):
            return f"Error: Zone field '{zone_field}' is not valid for dataset '{in_zone_data}'."
        
        # Define valid statistics.
        valid_stats = [
            "ALL", "MEAN", "MAJORITY", "MAJORITY_COUNT", "MAJORITY_PERCENT", "MAXIMUM", "MEDIAN",
            "MINIMUM", "MINORITY", "MINORITY_COUNT", "MINORITY_PERCENT", "PERCENTILE", "RANGE", "STD",
            "SUM", "VARIETY", "MIN_MAX", "MEAN_STD", "MIN_MAX_MEAN", "MAJORITY_VALUE_COUNT_PERCENT",
            "MINORITY_VALUE_COUNT_PERCENT"
        ]
        
        # Convert statistics_type to a list.
        if isinstance(statistics_type, str):
            statistics_list = [statistics_type.upper()]
        elif isinstance(statistics_type, list):
            statistics_list = [stat.upper() for stat in statistics_type]
        else:
            return "Error: statistics_type must be a string or a list of strings."
        
        # Validate each statistic.
        for stat in statistics_list:
            if stat not in valid_stats:
                return f"Error: Invalid statistic '{stat}'. Valid options are: {', '.join(valid_stats)}"
        
        # If "ALL" is specified (either as the only item or in a list), call the tool directly.
        if statistics_list == ["ALL"]:
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data,
                zone_field,
                in_value_raster,
                out_table,
                ignore_nodata,
                "ALL",
                process_as_multidimensional,
                percentile_values,
                percentile_interpolation_type,
                circular_calculation,
                circular_wrap_value,
                out_join_layer
            )
            return f"Successfully calculated zonal statistics (ALL) to '{out_table}'."
        
        # If only one statistic is requested, call the tool directly.
        if len(statistics_list) == 1:
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data,
                zone_field,
                in_value_raster,
                out_table,
                ignore_nodata,
                statistics_list[0],
                process_as_multidimensional,
                percentile_values,
                percentile_interpolation_type,
                circular_calculation,
                circular_wrap_value,
                out_join_layer
            )
            return f"Successfully calculated zonal statistics ({statistics_list[0]}) to '{out_table}'."
        
        # For multiple statistics, process each statistic separately and merge results.
        temp_tables = []
        for stat in statistics_list:
            temp_table = f"in_memory/temp_{stat.lower()}"
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data,
                zone_field,
                in_value_raster,
                temp_table,
                ignore_nodata,
                stat,
                process_as_multidimensional,
                percentile_values,
                percentile_interpolation_type,
                circular_calculation,
                circular_wrap_value,
                out_join_layer
            )
            temp_tables.append((temp_table, stat))
        
        # Copy the first temporary table to the final output.
        arcpy.management.CopyRows(temp_tables[0][0], out_table)
        
        # Join additional statistic fields from remaining temporary tables.
        for temp_table, stat in temp_tables[1:]:
            # Assume the field in each temp table is named exactly as the statistic.
            arcpy.management.JoinField(out_table, zone_field, temp_table, zone_field, [stat])
        
        # Clean up temporary tables.
        for temp_table, _ in temp_tables:
            arcpy.management.Delete(temp_table)
        
        return f"Successfully calculated zonal statistics {statistics_list} and merged results into '{out_table}'."
    
    except arcpy.ExecuteError:
        return f"Error executing tool: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

# @tool
# def zonal_statistics(in_zone_data: str, zone_field: str, in_value_raster: str, out_table: str,
#                     statistics_type: str = "MEAN") -> str:
#     """Calculates zonal statistics for each zone in a zone dataset.

#     Args:
#         in_zone_data: The path to the input zone dataset (feature class or raster).
#         zone_field: The field defining the zones.
#         in_value_raster: The path to the input value raster.
#         out_table: The path to the output table.
#         statistics_type: The statistic to calculate (e.g., "MEAN", "SUM", "MINIMUM", "MAXIMUM").
#     """
#     try:
#         if not _dataset_exists(in_zone_data):
#             return f"Error: Input zone dataset '{in_zone_data}' does not exist."
#         if not _dataset_exists(in_value_raster):
#             return f"Error: Input value raster '{in_value_raster}' does not exist."
#         if not _is_valid_field_name(in_zone_data, zone_field):
#             return f"Error: Zone field is not a valid field"

#         valid_stats = ["MEAN", "SUM", "MINIMUM", "MAXIMUM", "RANGE", "STD", "VARIETY", "MAJORITY", "MINORITY", "MEDIAN"]
#         if statistics_type.upper() not in valid_stats:
#             return f"Error: Invalid statistics_type. Must be one of: {', '.join(valid_stats)}"

#         arcpy.sa.ZonalStatisticsAsTable(in_zone_data, zone_field, in_value_raster, out_table, statistics_type=statistics_type.upper())
#         return f"Successfully calculated zonal statistics to '{out_table}'."
#     except arcpy.ExecuteError:
#         return f"Error calculating zonal statistics: {arcpy.GetMessages()}"
#     except Exception as e:
#         return f"An unexpected error occurred: {str(e)}"

@tool
def extract_by_mask(in_raster: str, in_mask_data: str, output_raster: str) -> str:
    """Extracts cells from a raster based on a mask.

    Args:
        in_raster: The path to the input raster.
        in_mask_data: The path to the mask dataset (feature class or raster).
        output_raster: The path to the output raster.
    """
    try:
        if not _dataset_exists(in_raster):
            return f"Error: Input raster '{in_raster}' does not exist."
        if not _dataset_exists(in_mask_data):
            return f"Error: Input mask dataset '{in_mask_data}' does not exist."

        out_raster_obj = arcpy.sa.ExtractByMask(in_raster, in_mask_data)
        out_raster_obj.save(output_raster)
        return f"Successfully extracted raster by mask to '{output_raster}'."
    except arcpy.ExecuteError:
        return f"Error extracting raster by mask: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def slope(in_raster: str, output_raster: str, output_measurement: str = "DEGREE", z_factor: float = 1.0) -> str:
    """Calculates the slope of a raster surface.

    Args:
        in_raster: The path to the input raster.
        output_raster: The path to the output slope raster.
        output_measurement: The units of the output slope ("DEGREE", "PERCENT_RISE").
        z_factor: The Z factor (for vertical exaggeration).
    """
    try:
        if not _dataset_exists(in_raster):
            return f"Error: Input raster '{in_raster}' does not exist."
        if output_measurement.upper() not in ("DEGREE", "PERCENT_RISE"):
            return "Error: Invalid output_measurement. Must be 'DEGREE' or 'PERCENT_RISE'."
        if not isinstance(z_factor, (int, float)):
            return "Error: z_factor must be a number"

        out_slope = arcpy.sa.Slope(in_raster, output_measurement.upper(), z_factor)
        out_slope.save(output_raster)
        return f"Successfully calculated slope to '{output_raster}'."
    except arcpy.ExecuteError:
        return f"Error calculating slope: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def aspect(in_raster: str, output_raster: str) -> str:
    """Calculates the aspect (direction) of a raster surface.

    Args:
        in_raster: The path to the input raster.
        output_raster: The path to the output aspect raster.
    """
    try:
        if not _dataset_exists(in_raster):
            return f"Error: Input raster '{in_raster}' does not exist."

        out_aspect = arcpy.sa.Aspect(in_raster)
        out_aspect.save(output_raster)
        return f"Successfully calculated aspect to '{output_raster}'."
    except arcpy.ExecuteError:
        return f"Error calculating aspect: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def hillshade(in_raster: str, output_raster: str, azimuth: float = 315.0, 
              altitude: float = 45.0, z_factor: float = 1.0) -> str:
    """Calculates the hillshade of a raster surface.

    Args:
        in_raster: The path to the input raster.
        output_raster: The path to the output hillshade raster.
        azimuth: The azimuth angle (0-360).
        altitude: The altitude angle (0-90).
        z_factor: The Z factor (for vertical exaggeration).
    """
    try:
        if not _dataset_exists(in_raster):
            return f"Error: Input raster '{in_raster}' does not exist."

        if not all(isinstance(arg, (int, float)) for arg in [azimuth, altitude, z_factor]):
            return "Error: Azimuth, altitude, and z_factor must be numbers."

        out_hillshade = arcpy.sa.Hillshade(in_raster, azimuth, altitude, "SHADOWS", z_factor)
        out_hillshade.save(output_raster)
        return f"Successfully calculated hillshade to '{output_raster}'."
    except arcpy.ExecuteError:
        return f"Error calculating hillshade: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def reclassify_raster(in_raster: str, reclass_field: str, remap_string: str, output_raster: str,
                      missing_values: str = "DATA") -> str:
    """Reclassifies (substitutes) values in a raster based on a reclassification table.

    Args:
        in_raster: The path to the input raster.
        reclass_field: The field to use for reclassification.
        remap_string: The reclassification mapping string (e.g., "1 5 1;5 10 2;10 20 3").
        output_raster: The path to the output reclassified raster.
        missing_values: How to handle missing values ("DATA" or "NODATA").
    """
    try:
        if not _dataset_exists(in_raster):
            return f"Error: Input raster '{in_raster}' does not exist."

        if missing_values.upper() not in ("DATA", "NODATA"):
            return "Error: Invalid 'missing_values'. Must be 'DATA' or 'NODATA'."

        remap_list = [item.strip().split() for item in remap_string.split(";")]
        remap = arcpy.sa.RemapValue(remap_list)

        out_reclass = arcpy.sa.Reclassify(in_raster, reclass_field, remap, missing_values.upper())
        out_reclass.save(output_raster)
        return f"Successfully reclassified raster to '{output_raster}'."
    except arcpy.ExecuteError:
        return f"Error reclassifying raster: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def define_projection(input_dataset: str, coor_system: str) -> str:
    """Defines the coordinate system for a dataset.

    Args:
        input_dataset: The path to the input dataset.
        coor_system: The coordinate system to define (e.g., a WKID, name, or path to a .prj file).
    """
    try:
        if not _dataset_exists(input_dataset):
            return f"Error: Input dataset '{input_dataset}' does not exist."

        try:
            sr = arcpy.SpatialReference(coor_system)
        except:
            return f"Error: Invalid coordinate system '{coor_system}'."

        arcpy.management.DefineProjection(input_dataset, sr)
        return f"Successfully defined projection for '{input_dataset}'."
    except arcpy.ExecuteError:
        return f"Error defining projection: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"




@tool
def list_fields(dataset: str) -> str:
    """Lists fields in a feature class or table, including alias names. 

    Args:
        dataset: The path to the feature class or table.
    """
    try:
        if not arcpy.Exists(dataset):
            return f"Error: Input dataset '{dataset}' does not exist."

        fields = arcpy.ListFields(dataset)
        
        # Create enhanced field info with additional information for case matching
        field_info = []
        for f in fields:
            field_data = {
                "field_name": f.name,
                "aliasName": f.aliasName,
                "type": f.type,
                "length": f.length,
                "precision": f.precision,
                "scale": f.scale,
                "isNullable": f.isNullable,
                "domain": f.domain,
                "editable": f.editable
            }
            
            # Add helpful hints for string fields that might be used in queries
            if f.type in ["String", "TEXT"]:
                # Get some sample values if possible (for small datasets)
                try:
                    with arcpy.da.SearchCursor(dataset, [f.name]) as cursor:
                        sample_values = []
                        for i, row in enumerate(cursor):
                            if i >= 5:  # Only get up to 5 sample values
                                break
                            if row[0] and str(row[0]).strip():  # Only add non-empty values
                                sample_values.append(str(row[0]))
                    
                    if sample_values:
                        field_data["sample_values"] = sample_values
                except:
                    pass
            
            field_info.append(field_data)
        
        # Add usage guidance to the result
        result = {
            "fields": field_info,
            "guidance": "For case-insensitive queries in where clauses, use the UPPER() function. Example: UPPER(field_name) = UPPER('Value')"
        }
        
        return json.dumps(result, indent=4)
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

    
@tool
def scan_workspace_directory_for_gis_files(workspace: str = None) -> str:
    """Lists all the files: datasets, feature classes, and tables in the current or specified workspace with detailed information.
    
    This tool provides a comprehensive inventory of the ArcGIS workspace contents, including:
    - Datasets with their types and counts
    - Feature classes with their geometry types, spatial references, and feature counts
    - Tables with their row counts
    
    Use it to find out all the gis files in the workspace and their information.
    Args:
        workspace (str, required): Path to the workspace (geodatabase or folder). 
    
    Returns:
        str: A JSON-formatted string containing:
            {
                "datasets": [
                    {
                        "name": str,  # Name of the dataset
                        "type": str,  # Dataset type (e.g., "FeatureDataset", "RasterDataset")
                    }
                ],
                "feature_classes": [
                    {
                        "name": str,  # Name of the feature class
                        "type": str,  # Shape type (e.g., "Polygon", "Point", "Polyline")
                        "spatial_reference": str,  # Spatial reference name
                        "feature_count": int  # Number of features in the feature class
                    }
                ],
                "tables": [
                    {
                        "name": str,  # Name of the table
                        "row_count": int  # Number of rows in the table
                    }
                ]  # List of tables with their row counts
            }
    
    Raises:
        arcpy.ExecuteError: If there's an error accessing the workspace or listing contents
    """

    try:
        if workspace:
            arcpy.env.workspace = workspace
            
        datasets = arcpy.ListDatasets()
        fcs = arcpy.ListFeatureClasses()
        tables = arcpy.ListTables()
        
        inventory = {
            "datasets": [
                {
                    "name": ds,
                    "type": arcpy.Describe(ds).datasetType
                } for ds in (datasets or [])
            ],
            "feature_classes": [
                {
                    "name": fc,
                    "type": arcpy.Describe(fc).shapeType,
                    "spatial_reference": arcpy.Describe(fc).spatialReference.name,
                    "feature_count": arcpy.GetCount_management(fc)[0]  # Count of features
                } for fc in (fcs or [])
            ],
            "tables": [
                {
                    "name": table,
                    "row_count": arcpy.GetCount_management(table)[0]  # Count of rows in the table
                } for table in (tables or [])
            ]
        }
        return json.dumps(inventory, indent=2)
    except arcpy.ExecuteError:
        return f"ArcGIS Error: {arcpy.GetMessages(2)}"


@tool
def download_landsat_tool(
    output_directory: str,
    start_date: str,
    end_date: str,
    max_cloud_cover: float = 20.0,
    landsat_sensors: List[str] = None,
    bands: List[str] = None,
    aoi_feature_class: str = None,
    bounding_box: str = None,
    delete_archive: bool = True,
    max_concurrent_downloads: int = 5,
) -> str:
    """Downloads Landsat Collection 2 Level-2 imagery (Surface Reflectance/Temperature) asynchronously via the USGS M2M API.

    This function automates the process of searching for, requesting, and downloading Landsat data.
    It handles authentication, scene searching, download option retrieval, batch download requests,
    polling for download URLs, downloading files, and (optionally) extracting tar archives.  It uses
    `asyncio` and `aiohttp` for concurrent downloads, significantly improving download speed.  `nest_asyncio`
    is used to allow for nested event loops, making it suitable for use in Jupyter notebooks and IPython.

    Args:
        output_directory: The directory where downloaded files and extracted data will be stored.
            This directory will be created if it doesn't exist.
        start_date: The start date for the imagery search (inclusive), in 'YYYY-MM-DD' format.
        end_date: The end date for the imagery search (inclusive), in 'YYYY-MM-DD' format.
        max_cloud_cover: The maximum acceptable cloud cover percentage (0-100).  Defaults to 20.0.
        landsat_sensors: A list of Landsat sensor identifiers to search for.  Valid options are
            "L8", "L9", "L7", and "L5". Defaults to ["L8", "L9"] if not specified.
        bands: A list of band identifiers to download.  If None, the entire product bundle is
            downloaded.  Band identifiers should be in the format "B1", "B2", etc. (e.g., ["B2", "B3", "B4"]).
            If specified, individual band files are downloaded instead of the full bundle.
        aoi_feature_class:  Not currently supported.  Reserved for future use with feature classes.
        bounding_box: A string defining the bounding box for the search, in the format
            "min_lon,min_lat,max_lon,max_lat" (WGS84 coordinates).
        delete_archive: If True (default), downloaded tar archives are deleted after extraction
            (only applicable when downloading full bundles, i.e., when `bands` is None).
        max_concurrent_downloads: The maximum number of concurrent downloads. Defaults to 5.  Higher
            values can improve download speed but may overwhelm your system or the server.

    Returns:
        A string summarizing the result of the download process, indicating the number of
        files/scenes downloaded and the output directory.  Returns an error message if any
        part of the process fails."""

    base_url = "https://m2m.cr.usgs.gov/api/api/json/stable/"

    def m2m_request(endpoint: str, payload: dict, apiKey: str = None) -> dict:
        url = base_url + endpoint
        headers = {}
        if apiKey:
            headers["X-Auth-Token"] = apiKey
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        resp_json = response.json()
        if resp_json.get("errorCode"):
            raise Exception(f"{resp_json.get('errorCode', 'Unknown Error')}: {resp_json.get('errorMessage', '')}")
        return resp_json.get("data")

    # --- Input validation and setup ---
    if not all([output_directory, start_date, end_date, bounding_box]):
        return "Error: output_directory, start_date, end_date, and bounding_box are required."
    os.makedirs(output_directory, exist_ok=True)

    try:
        min_lon, min_lat, max_lon, max_lat = map(float, bounding_box.split(","))
        if not (-180 <= min_lon <= 180 and -90 <= min_lat <= 90 and -180 <= max_lon <= 180 and -90 <= max_lat <= 90):
            raise ValueError()
    except (ValueError, TypeError):
        return "Error: Invalid bounding_box format. Use 'min_lon,min_lat,max_lon,max_lat'."

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return "Error: Invalid date format. Use 'YYYY-MM-DD'."

    if landsat_sensors is None:
        landsat_sensors = ["L8", "L9"]

    # 2. Authentication
    username = os.getenv("EARTHDATA_USER")
    token = os.getenv("EARTHDATA_TOKEN")
    if not username or not token:
        return "Error: EARTHDATA_USER and EARTHDATA_TOKEN environment variables must be set."

    login_payload = {"username": username, "token": token}
    try:
        apiKey = m2m_request("login-token", login_payload)
        print("Login successful.")
    except Exception as e:
        return f"Login failed: {str(e)}"

    # 3. Scene Search
    datasets_map = {
        "L8": "landsat_ot_c2_l2",
        "L9": "landsat_ot_c2_l2",
        "L7": "landsat_etm_c2_l2",
        "L5": "landsat_tm_c2_l2"
    }
    scene_list = []
    for sensor in landsat_sensors:
        sensor_key = sensor.upper()
        if sensor_key not in datasets_map:
            m2m_request("logout", {}, apiKey)
            return f"Error: Invalid sensor '{sensor}'."
        dataset = datasets_map[sensor_key]
        search_payload = {
            "datasetName": dataset,
            "sceneFilter": {
                "spatialFilter": {"filterType": "geojson", "geoJson": {
                    "type": "Polygon",
                    "coordinates": [[
                        [min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, min_lat], [min_lon, min_lat]
                    ]]
                }},
                "acquisitionFilter": {"start": start_date, "end": end_date},
                "cloudCoverFilter": {"min": 0, "max": int(max_cloud_cover)}
            }
        }
        try:
            search_data = m2m_request("scene-search", search_payload, apiKey)
            results = search_data.get("results", [])
            print(f"Found {len(results)} scenes for sensor {sensor_key}.")
            scene_list.extend([(scene.get("entityId"), dataset, scene.get("displayId"))
                               for scene in results if scene.get("entityId") and scene.get("displayId")])
        except Exception as e:
            m2m_request("logout", {}, apiKey)
            return f"Search failed for sensor {sensor_key}: {str(e)}"

    if not scene_list:
        m2m_request("logout", {}, apiKey)
        return "No scenes found."

    entity_to_display = {entityId: displayId for entityId, _, displayId in scene_list}

    # 4. Download Options
    downloads = []
    dataset_groups: Dict[str, List[str]] = {}
    for entityId, ds, _ in scene_list:
        dataset_groups.setdefault(ds, []).append(entityId)


    if bands is None:
        # Full bundle workflow
        for ds, entityIds in dataset_groups.items():
            payload = {"datasetName": ds, "entityIds": entityIds}
            try:
                dload_data = m2m_request("download-options", payload, apiKey)
                if isinstance(dload_data, list):
                    options = dload_data
                elif isinstance(dload_data, dict):
                    options = dload_data.get("options", [])
                else:
                    options = []
                options_by_entity: Dict[str, dict] = {}
                for opt in options:
                    if opt.get("available"):
                        ent_id = opt.get("entityId")
                        if ent_id and ent_id not in options_by_entity:
                            options_by_entity[ent_id] = opt
                for ent in entityIds:
                    if ent in options_by_entity:
                        opt = options_by_entity[ent]
                        downloads.append({"entityId": ent, "productId": opt.get("id")})
                # Removed: No longer needed for verbose output: print(f"Retrieved bundle download options for dataset {ds}.")
            except Exception as e:
                print(f"Download-options request failed for dataset {ds}: {str(e)}")  # Keep: Important for error handling

    else:  # Specific bands
        for dataset_name, entity_ids in dataset_groups.items():
            payload = {"datasetName": dataset_name, "entityIds": entity_ids}
            try:
                options = m2m_request("download-options", payload, apiKey)
                if isinstance(options, dict):
                    options = options.get("options", [])
                options_by_entity = {opt["entityId"]: opt for opt in options if opt.get("available") and opt.get("entityId")}

                for entity_id in entity_ids:
                    if entity_id in options_by_entity:
                        option = options_by_entity[entity_id]
                        for secondary_option in option.get("secondaryDownloads", []):
                            if secondary_option.get("available"):
                                file_id = secondary_option.get("displayId", "")
                                if any(file_id.endswith(f"_{band_code.upper()}.TIF") for band_code in bands):
                                    downloads.append({"entityId": secondary_option["entityId"], "productId": secondary_option["id"]})
            except Exception as e:
                print(f"Download-options request failed for dataset {dataset_name}: {str(e)}")

    if not downloads:
        m2m_request("logout", {}, apiKey)
        return "No available downloads found."

    # 5. Download Request
    label = datetime.now().strftime("%Y%m%d_%H%M%S")
    req_payload = {"downloads": downloads, "label": label}
    try:
        req_results = m2m_request("download-request", req_payload, apiKey)
        print("Download request submitted.")
        available_downloads = req_results.get("availableDownloads", [])
        preparing_downloads = req_results.get("preparingDownloads", [])
    except Exception as e:
        m2m_request("logout", {}, apiKey)
        return f"Download request failed: {str(e)}"

    # 6. Poll for Download URLs (if needed) - CORRECTED LOGIC
    if preparing_downloads:  # Poll if *anything* is preparing
        retrieve_payload = {"label": label}
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                ret_data = m2m_request("download-retrieve", retrieve_payload, apiKey)
                if ret_data and ret_data.get("available"):
                    available_downloads.extend(ret_data["available"])  # Add new URLs
                    print(f"Attempt {attempt + 1}: Retrieved {len(ret_data['available'])} URLs.")
                    if len(available_downloads) >= len(downloads):
                        break  # Exit loop when we have all URLs
                else:
                    print("No download URLs retrieved yet.")
            except Exception as e:
                print(f"Download-retrieve attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_attempts - 1:
                print(f"Waiting 20 seconds... ({attempt + 1}/{max_attempts})")
                time.sleep(20)


    # 7. Download and Process (ASYNC)
    async def _download_and_process(downloads_to_process):
        async def _download_single_file(session, item, semaphore):
            async with semaphore:
                download_url = item.get("url")
                if not download_url:
                    return None

                try:
                    async with session.get(download_url, timeout=300) as response:
                        response.raise_for_status()

                        if bands is not None:
                            new_fname = item.get("fileName")
                            if not new_fname:
                                entity_id = item.get("entityId")
                                if entity_id:
                                    new_fname = entity_id + ".TIF"
                                else:
                                    print(f"Warning: entityId missing, skipping: {item}")
                                    return None
                        else:
                            entity = item.get("entityId")
                            display_id = entity_to_display.get(entity)
                            new_fname = (display_id + ".tar.gz") if display_id else os.path.basename(urlparse(download_url).path)

                        final_path = os.path.join(output_directory, new_fname)
                        async with aiofiles.open(final_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        print(f"Downloaded: {new_fname}")

                        if bands is None and new_fname.endswith(".tar.gz"):
                            try:
                                with tarfile.open(final_path, "r:*") as tar:
                                    extract_dir = os.path.join(output_directory, entity_to_display.get(item.get("entityId"), ""))
                                    os.makedirs(extract_dir, exist_ok=True)
                                    tar.extractall(path=extract_dir)
                                print(f"Extracted: {new_fname}")
                                if delete_archive:
                                    os.remove(final_path)
                                    print(f"Deleted archive: {final_path}")
                            except Exception as e:
                                print(f"Error extracting {final_path}: {str(e)}")
                        return final_path

                except Exception as e:
                    print(f"Download failed for {download_url}: {str(e)}")
                    return None

        semaphore = asyncio.Semaphore(max_concurrent_downloads)
        async with aiohttp.ClientSession() as session:
            tasks = [_download_single_file(session, item, semaphore) for item in downloads_to_process]
            return await asyncio.gather(*tasks)

    downloaded_files: List[str] = []
    try:
        # ALWAYS process available_downloads
        downloaded_files = asyncio.run(_download_and_process(available_downloads))
        downloaded_files = [path for path in downloaded_files if path is not None]  # Filter out failures

    except RuntimeError as e:
        print(f"RuntimeError: {e}")

    # 8. Logout
    try:
        m2m_request("logout", {}, apiKey)
        print("Logged out.")
    except Exception as e:
        print(f"Logout failed: {str(e)}")

    return f"Successfully downloaded {len(downloaded_files)} files to {output_directory}."


@tool
def scan_external_directory_for_gis_files(directory_path: str) -> str:
    """Scans a directory for GIS-compatible files and returns their details. 
    These directories are external directories that are not part of the workspace (inside the geodatabases).
    
    Args:
        directory_path: Path to the directory to scan
        
    Returns:
        JSON string containing file information categorized by type:
        {
            "vector_files": [
                {
                    "name": str,
                    "path": str,
                    "type": str,  # "Shapefile", "GeoJSON", etc.
                    "driver": str,
                    "layer_count": int,
                    "crs": str
                }
            ],
            "raster_files": [
                {
                    "name": str,
                    "path": str,
                    "type": str,  # "GeoTIFF", "IMG", etc.
                    "dimensions": [width, height],
                    "bands": int,
                    "crs": str
                }
            ]
        }
    """
    try:
        print(f"Scanning directory: {directory_path}")
        if not os.path.exists(directory_path):
            print(f"Directory does not exist: {directory_path}")
            return json.dumps({"error": f"Directory does not exist: {directory_path}"})
        
        # File extensions to look for
        vector_extensions = {'.shp', '.geojson', '.gml', '.kml', '.gpkg', '.json', '.zip'}
        raster_extensions = {'.tif', '.tiff', '.img', '.dem', '.hgt', '.asc', '.jpg', '.jpeg', '.png', '.bmp'}
        
        result = {
            "vector_files": [],
            "raster_files": []
        }
        
        # Count files for logging
        total_files = 0
        vector_files_found = 0
        raster_files_found = 0
        
        print(f"Starting directory walk in {directory_path}")
        for root, dirs, files in os.walk(directory_path):
            print(f"Scanning subdirectory: {root} with {len(files)} files")
            for file in files:
                total_files += 1
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                
                # Vector files
                if ext in vector_extensions:
                    try:
                        print(f"Attempting to open vector file: {file_path}")
                        with fiona.open(file_path) as src:
                            vector_files_found += 1
                            result["vector_files"].append({
                                "name": file,
                                "path": file_path,
                                "type": src.driver,
                                "driver": src.driver,
                                "layer_count": len(src),
                                "crs": str(src.crs)
                            })
                            print(f"Successfully processed vector file: {file_path}")
                    except Exception as e:
                        print(f"Error processing vector file {file_path}: {str(e)}")
                
                # Raster files
                elif ext in raster_extensions:
                    try:
                        print(f"Attempting to open raster file: {file_path}")
                        with rasterio.open(file_path) as src:
                            raster_files_found += 1
                            result["raster_files"].append({
                                "name": file,
                                "path": file_path,
                                "type": src.driver,
                                "dimensions": [src.width, src.height],
                                "bands": src.count,
                                "crs": str(src.crs)
                            })
                            print(f"Successfully processed raster file: {file_path}")
                    except Exception as e:
                        print(f"Error processing raster file {file_path}: {str(e)}")
        
        print(f"Scan complete for {directory_path}:")
        print(f"  Total files scanned: {total_files}")
        print(f"  Vector files found: {vector_files_found}")
        print(f"  Raster files found: {raster_files_found}")
        
        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = f"Error scanning directory {directory_path}: {str(e)}"
        print(error_msg)
        traceback.print_exc()  # Print the full traceback for debugging
        return json.dumps({"error": error_msg})

@tool
def raster_calculator(input_rasters: List[str], expression: str, output_raster: str) -> str:
    """Performs calculations on rasters using map algebra expressions.
    
    This tool allows you to perform mathematical operations on raster datasets using map algebra.
    Each input raster is referenced in the expression as 'r1', 'r2', etc., in the order they appear 
    in the input_rasters list. The calculation is performed on a cell-by-cell basis.
    
    GIS Concepts:
    - Map algebra allows mathematical operations on raster cells
    - Operations are performed on a cell-by-cell basis
    - Common uses include terrain analysis, vegetation indices, raster reclassification
    - Can create new derived datasets from existing rasters
    
    Args:
        input_rasters: List of raster paths to use in the calculation. 
                      Each raster will be referenced in the expression as 'r1', 'r2', etc.
                      All rasters must be valid and accessible.
        expression: A valid map algebra expression using the references 'r1', 'r2', etc.
                   Can include mathematical operators (+, -, *, /), functions (Abs, Sin, Cos),
                   and logical operators (<, >, ==, etc.).
        output_raster: Path to save the result raster.
                      Will be overwritten if it already exists.
    
    Returns:
        A message indicating success or failure with details about the operation.
        
    Example:
        >>> raster_calculator(["dem1.tif", "dem2.tif"], "(r1 + r2) / 2", "average_dem.tif")
        "Successfully calculated and saved raster to 'average_dem.tif'."
        
        >>> raster_calculator(["landsat_nir.tif", "landsat_red.tif"], "(r1 - r2) / (r1 + r2)", "ndvi.tif")
        "Successfully calculated and saved raster to 'ndvi.tif'."
    
    Notes:
        - Requires Spatial Analyst extension
        - Expression syntax must be valid Python that evaluates to a raster
        - All input rasters should have the same spatial resolution and extent for best results
        - Output will have the same spatial reference as the inputs
    """
    try:
        # Input validation
        if not input_rasters:
            return "Error: No input rasters provided."
            
        # Validate that all input rasters exist
        for i, raster in enumerate(input_rasters):
            if not _validate_raster_exists(raster):
                return f"Error: Input raster '{raster}' does not exist or is not a valid raster."
        
        # Create references to the input rasters
        rasters = {}
        for i, raster_path in enumerate(input_rasters):
            raster_var = f"r{i+1}"
            rasters[raster_var] = arcpy.Raster(raster_path)
        
        # Replace raster references in the expression
        calc_expression = expression
        for var_name, raster_obj in rasters.items():
            # This approach preserves the expression as is, letting arcpy's Raster Calculator handle it
            locals()[var_name] = raster_obj
        
        # Execute the calculation using the spatial analyst extension
        arcpy.CheckOutExtension("Spatial")
        try:
            # Use eval to create the raster algebra expression
            result_raster = eval(calc_expression)
            result_raster.save(output_raster)
            arcpy.CheckInExtension("Spatial")
            return f"Successfully calculated and saved raster to '{output_raster}'."
        except SyntaxError:
            return f"Error: Invalid expression syntax: {expression}"
        except Exception as e:
            return f"Error in raster calculation: {str(e)}"
        finally:
            arcpy.CheckInExtension("Spatial")
    except arcpy.ExecuteError:
        return f"ArcPy error: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


@tool
def calculate_ndvi(nir_band: str, red_band: str, output_raster: str) -> str:
    """Calculates Normalized Difference Vegetation Index (NDVI) from NIR and Red bands.
    
    NDVI is one of the most common vegetation indices used to assess vegetation health and density.
    The formula is: NDVI = (NIR - Red) / (NIR + Red)
    
    NDVI values range from -1 to 1, where:
    - Higher values (0.6 to 1.0): Dense, healthy vegetation
    - Moderate values (0.2 to 0.5): Sparse vegetation
    - Low values (0 to 0.1): Bare soil, rocks, urban areas
    - Negative values: Water, snow, clouds
    
    GIS Concepts:
    - NDVI uses the contrast between red light absorption and NIR reflection by vegetation
    - Healthy plants absorb red light for photosynthesis and reflect NIR
    - NDVI is useful for monitoring vegetation health, drought, agricultural productivity
    - It can help identify seasonal changes and long-term vegetation trends
    
    Args:
        nir_band: The path to the NIR (Near Infrared) band raster.
                 For Landsat 8-9, this is typically Band 5.
                 For Sentinel-2, this is typically Band 8.
        red_band: The path to the Red band raster.
                 For Landsat 8-9, this is typically Band 4.
                 For Sentinel-2, this is typically Band 4.
        output_raster: The path to save the output NDVI raster.
                      Will be overwritten if it already exists.
    
    Returns:
        A message indicating success or failure with details about the operation.
        
    Example:
        >>> calculate_ndvi("landsat8_B5.tif", "landsat8_B4.tif", "ndvi_result.tif")
        "Successfully calculated NDVI and saved to 'ndvi_result.tif'."
    
    Notes:
        - Requires Spatial Analyst extension
        - Input bands should be from the same image/date
        - Both bands should have the same spatial resolution and extent
        - Output values range from -1 to 1, with higher values indicating healthier vegetation
        - Common transformations include scaling to 0-255 or 0-100 for visualization
    """
    try:
        # Validate inputs
        if not _validate_raster_exists(nir_band):
            return f"Error: NIR band raster '{nir_band}' does not exist or is not a valid raster."
        
        if not _validate_raster_exists(red_band):
            return f"Error: Red band raster '{red_band}' does not exist or is not a valid raster."
        
        # Execute NDVI calculation
        arcpy.CheckOutExtension("Spatial")
        try:
            nir = arcpy.Raster(nir_band)
            red = arcpy.Raster(red_band)
            
            # Calculate NDVI: (NIR - Red) / (NIR + Red)
            ndvi = arcpy.sa.Float(nir - red) / arcpy.sa.Float(nir + red)
            ndvi.save(output_raster)
            
            arcpy.CheckInExtension("Spatial")
            return f"Successfully calculated NDVI and saved to '{output_raster}'."
        except Exception as e:
            return f"Error in NDVI calculation: {str(e)}"
        finally:
            arcpy.CheckInExtension("Spatial")
    except arcpy.ExecuteError:
        return f"ArcPy error: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def calculate_savi(nir_band: str, red_band: str, output_raster: str,
                  soil_factor: float = 0.5) -> str:
    """Calculate Soil-Adjusted Vegetation Index (SAVI).
    
    SAVI = [(NIR - Red) / (NIR + Red + L)] * (1 + L)
    where L is a soil adjustment factor (usually 0.5).
    
    SAVI is similar to NDVI but accounts for soil brightness variations.
    
    Args:
        nir_band: The path to the NIR band raster.
        red_band: The path to the Red band raster.
        output_raster: The path to the output SAVI raster.
        soil_factor: The soil adjustment factor (L). Default is 0.5.
                    Values range from 0 (high vegetation) to 1 (low vegetation).
    
    Returns:
        A message indicating success or failure.
    """
    try:
        # Validate inputs
        if not _validate_raster_exists(nir_band):
            return f"Error: NIR band raster '{nir_band}' does not exist or is not a valid raster."
        
        if not _validate_raster_exists(red_band):
            return f"Error: Red band raster '{red_band}' does not exist or is not a valid raster."
        
        if not isinstance(soil_factor, (int, float)) or soil_factor < 0 or soil_factor > 1:
            return "Error: soil_factor must be a number between 0 and 1."
        
        # Execute SAVI calculation
        arcpy.CheckOutExtension("Spatial")
        try:
            nir = arcpy.Raster(nir_band)
            red = arcpy.Raster(red_band)
            
            # Calculate SAVI: [(NIR - Red) / (NIR + Red + L)] * (1 + L)
            numerator = nir - red
            denominator = nir + red + soil_factor
            savi = arcpy.sa.Float(numerator) / arcpy.sa.Float(denominator) * (1 + soil_factor)
            savi.save(output_raster)
            
            arcpy.CheckInExtension("Spatial")
            return f"Successfully calculated SAVI and saved to '{output_raster}'."
        except Exception as e:
            return f"Error in SAVI calculation: {str(e)}"
        finally:
            arcpy.CheckInExtension("Spatial")
    except arcpy.ExecuteError:
        return f"ArcPy error: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@tool
def calculate_tpi(dem_raster: str, output_raster: str, neighborhood_size: int = 3) -> str:
    """Calculate Topographic Position Index (TPI).
    
    TPI compares the elevation of each cell in a DEM to the mean elevation of a specified neighborhood around that cell.
    Positive values indicate locations higher than their surroundings (ridges, peaks),
    negative values indicate locations lower than their surroundings (valleys, pits),
    and values near zero indicate flat areas or areas of constant slope.
    
    Args:
        dem_raster: The path to the input Digital Elevation Model (DEM) raster.
        output_raster: The path to the output TPI raster.
        neighborhood_size: The size of the neighborhood in cells. Default is 3 (3x3 neighborhood).
    
    Returns:
        A message indicating success or failure.
    """
    try:
        # Validate inputs
        if not _validate_raster_exists(dem_raster):
            return f"Error: DEM raster '{dem_raster}' does not exist or is not a valid raster."
        
        if not isinstance(neighborhood_size, int) or neighborhood_size < 3 or neighborhood_size % 2 == 0:
            return "Error: neighborhood_size must be an odd integer greater than or equal to 3."
        
        # Execute TPI calculation
        arcpy.CheckOutExtension("Spatial")
        try:
            # Create a neighborhood object
            neighborhood = arcpy.sa.NbrRectangle(neighborhood_size, neighborhood_size, "CELL")
            
            # Calculate focal statistics (mean elevation in the neighborhood)
            mean_elevation = arcpy.sa.FocalStatistics(
                dem_raster,
                neighborhood,
                "MEAN",
                "NODATA")
            
            # Calculate TPI: Original value - neighborhood mean
            dem = arcpy.Raster(dem_raster)
            tpi = dem - mean_elevation
            
            tpi.save(output_raster)
            
            arcpy.CheckInExtension("Spatial")
            return f"Successfully calculated TPI and saved to '{output_raster}'."
        except Exception as e:
            return f"Error in TPI calculation: {str(e)}"
        finally:
            arcpy.CheckInExtension("Spatial")
    except arcpy.ExecuteError:
        return f"ArcPy error: {arcpy.GetMessages()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"
    
@tool
def search_arcgis_online_content(
    base_query: str = "",
    title: Optional[str] = None,
    item_type: Optional[str] = None,
    owner: Optional[str] = None,
    tags: Optional[Union[str, List[str]]] = None,
    typeKeywords: Optional[Union[str, List[str]]] = None,
    snippet: Optional[str] = None,
    group_id: Optional[str] = None,
    categories: Optional[Union[str, List[str]]] = None,
    created_start_date: Optional[str] = None, # YYYY-MM-DD
    created_end_date: Optional[str] = None,   # YYYY-MM-DD
    max_results: int = 20,
    search_living_atlas_focused: bool = False,
    search_outside_org: bool = True
) -> str:
    """Searches ArcGIS Online/Portal for GIS items using advanced filtering based on the REST API query syntax.

    Allows flexible searching using keywords and various filters like title, item type, owner,
    tags, typeKeywords, description, snippet, created date, group ID,
    and categories. Constructs queries following ArcGIS REST API standards.
    Does NOT perform complex spatial filtering (like polygon intersects) during the item search itself;
    use location names in the 'query' argument for geographic focus.
    Results are sorted by relevance descending by default.
    Suggestions for improving search results:
    - Use specific keywords or phrases in the query (e.g., 'california population density').
    - Searching using the title and snippet fields often yields the best results if described properly. Always use title, it can be the same as the base query as well.
    - Always leave the Base query as an empty string and use the title to serch for specific items.
    - Use tags and typeKeywords to filter results to specific content types or themes.
    - Only use Feature Service, and Image Service item types for the search.
    - Do not modify the max_results parameter unless necessary.
    - Do not use the owner parameter unless the user is looking for specific content from a specific owner.
    
    GIS Concepts:
    - Content Search: Finding GIS items based on metadata. Uses Lucene query syntax.
    - Item Metadata Fields: title, tags, snippet, description, type, typeKeywords, owner, created, id, access, categories, group.
    - Living Atlas Focus: Option to prioritize searching common Living Atlas sources if no specific owner/group/tags are given.

    Args:
        base_query: The primary keyword search string (e.g., "california population density", "hospitals near main street london"). Can include boolean operators (AND, OR, NOT) and field searches (e.g., 'title:"San Francisco"').
        title: (Optional) Filter by item title. Exact match using 'title:"value"'.
        item_type: (Optional) Filter by item type (e.g., 'Feature Service', 'Image Service'). Use exact case and quotes: 'type:"Web Map"'.
        owner: (Optional) Filter by the username of the item owner (e.g., 'esri', 'fedmaps_usgs'). Uses 'owner:"value"'.
        tags: (Optional) Filter by tags. Single tag string or list. Items must have ALL specified tags. Uses 'tags:"value"' or '(tags:"tag1" AND tags:"tag2")'.
        typeKeywords: (Optional) Filter by type keywords. Single string or list. Uses 'typeKeywords:"value"'.
        snippet: (Optional) Search within the item snippet (summary). Uses 'snippet:"value"'.
        group_id: (Optional) Filter by the ID of a specific group. Uses 'group:"value"'.
        categories: (Optional) Filter by organization content categories. Single string or list. Uses 'categories:"value"'.
        created_start_date: (Optional) Filter items created on or after this date (YYYY-MM-DD).
        created_end_date: (Optional) Filter items created on or before this date (YYYY-MM-DD).
        max_results: (Optional) Max number of results (default: 10).
        search_living_atlas_focused: (Optional) If True and owner/tags/group_id are NOT specified, adds filters for common Living Atlas owners/tags.
        search_outside_org: (Optional) If True (default), searches content outside the user's organization (implies public or shared content depending on context). If False, searches only within the user's organization. This controls the `outside_org` parameter of `gis.content.search`. An `access:public` filter is added explicitly if True.

    Returns:
        A JSON string representing a list of found items (including title, id, type, owner, snippet, description, tags, created date).
        Returns an error message string on failure or if no items are found.

    Example Use by AI:
        # User: "Find recent wildfire Web Maps in California from CALFIRE_Agency"
        >>> search_arcgis_content(query="wildfire california", owner="CALFIRE_Agency", created_start_date="2024-01-01", item_type="Web Map") # Example uses created_start_date now

        # User: "Show me authoritative elevation layers for Mount Rainier area"
        >>> search_arcgis_content(query="elevation DEM Mount Rainier", item_type="Imagery Layer", search_living_atlas_focused=True) # Removed contentStatus

        # User: "Search for census data tagged 'population' and '2020' with type keyword 'Demographics'"
        >>> search_arcgis_content(query="census", tags=["population", "2020"], typeKeywords="Demographics", item_type="Feature Service")

        # User: "Find public transport layers for London created this year within org 'MyOrgID'"
        >>> search_arcgis_content(query="public transport london", item_type="Feature Service", created_start_date="2025-01-01", search_outside_org=False) # Removed orgid, Assuming current year 2025
    """
    gis = get_gis_connection()
    if not gis:
        return "Error: Failed to establish connection to ArcGIS. Check Credentials/Network."

    # --- Input Validation ---
    if not isinstance(base_query, str): # Allow empty query if other filters are used
        return "Error: query must be a string."
    if not isinstance(max_results, int) or max_results <= 0:
        return "Error: max_results must be a positive integer."

    def _validate_and_format_date_for_api(date_str: Optional[str]) -> Optional[int]:
        """Parses YYYY-MM-DD input and returns milliseconds since epoch for API query."""
        if not date_str: return None
        try:
            # Parse the date string
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            # Convert to timestamp (seconds since epoch) and then to milliseconds
            timestamp_ms = int(dt.timestamp() * 1000)
            return timestamp_ms
        except ValueError:
            raise ValueError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD.")

    def _format_list_filter(field_name: str, values: Optional[Union[str, List[str]]]) -> Optional[str]:
        """Formats a list of values for a field query (e.g., tags, typeKeywords)."""
        if not values: return None
        value_list = [values] if isinstance(values, str) else values
        processed_values = []
        for val in value_list:
            if isinstance(val, str) and val.strip():
                # Quote values, especially if they contain spaces
                val_formatted = f'"{val.strip()}"'
                processed_values.append(f'{field_name}:{val_formatted}')
        if not processed_values: return None
        # Combine multiple values with AND logic as per documentation examples
        return "(" + " AND ".join(processed_values) + ")" if len(processed_values) > 1 else processed_values[0]

    try:
        # Validate dates before building query
        created_start_ms = _validate_and_format_date_for_api(created_start_date)
        created_end_ms = _validate_and_format_date_for_api(created_end_date)


        # --- Build Query String Dynamically using REST API syntax ---
        query_parts = []
        if base_query.strip():
             # Wrap base query in parentheses if it contains spaces or operators, to be safe
             if ' ' in base_query.strip() or any(op in base_query for op in [' AND ', ' OR ', ' NOT ']):
                 query_parts.append(f"({base_query.strip()})")
             else:
                 query_parts.append(base_query.strip())


        # Add specific field filters
        if title and isinstance(title, str) and title.strip():
            query_parts.append(f'title:"{title.strip()}"')
        if item_type and isinstance(item_type, str) and item_type.strip():
             # Item types often need exact case and quotes
            query_parts.append(f'type:"{item_type.strip()}"')
        if owner and isinstance(owner, str) and owner.strip():
            query_parts.append(f'owner:"{owner.strip()}"')
        if snippet and isinstance(snippet, str) and snippet.strip():
            query_parts.append(f'snippet:"{snippet.strip()}"')
        if group_id and isinstance(group_id, str) and group_id.strip():
             query_parts.append(f'group:"{group_id.strip()}"')


        # Handle list-based filters
        tags_filter = _format_list_filter("tags", tags)
        if tags_filter: query_parts.append(tags_filter)

        typeKeywords_filter = _format_list_filter("typeKeywords", typeKeywords)
        if typeKeywords_filter: query_parts.append(typeKeywords_filter)

        categories_filter = _format_list_filter("categories", categories)
        if categories_filter: query_parts.append(categories_filter)


        # Date range handling (inclusive using milliseconds)
        def format_date_range_ms(field: str, start_ms: Optional[int], end_ms: Optional[int]) -> Optional[str]:
            if start_ms is None and end_ms is None:
                return None
            start = start_ms if start_ms is not None else "*"
            end = end_ms if end_ms is not None else "*"
            # Ensure start is not greater than end if both are specified
            if isinstance(start, int) and isinstance(end, int) and start > end:
                 raise ValueError(f"Start date cannot be after end date for {field}.")
            return f"{field}:[{start} TO {end}]"

        created_range = format_date_range_ms("created", created_start_ms, created_end_ms)
        if created_range: query_parts.append(created_range)


        # Handle Living Atlas focus: Apply ONLY if no specific owner/group/tags were provided
        specific_filters_provided = bool(owner or tags or group_id) # Removed orgid check
        if search_living_atlas_focused and not specific_filters_provided:
            # Add common LA owners/tags - adjust as needed based on current best practices
            la_filter = '(owner:esri OR owner:"esri_livingatlas" OR owner:"LivingAtlas" OR tags:"Living Atlas")'
            query_parts.append(la_filter)

        # Handle access filter based on search_outside_org
        # If searching outside org, explicitly add access:public for clarity and broader reach
        if search_outside_org:
            query_parts.append("access:public")
        # If search_outside_org is False, we rely on the API's default behavior
        # which searches within the user's org content when authenticated.

        # Combine all parts with AND
        final_query = " AND ".join(filter(None, query_parts)) # Filter out any None parts

        if not final_query:
             return "Error: No valid search criteria provided. Please specify a query or at least one filter."

        print(f"Executing ArcGIS Content search query: {final_query}")
        print(f"Searching outside organization: {search_outside_org}")

        # --- Execute Search ---
        # Pass the constructed query string to gis.content.search
        # The outside_org parameter controls whether to search beyond the user's org content
        search_results = gis.content.search(
            query=final_query,
            max_items=max_results,
            outside_org=search_outside_org
        )

        # --- Format Results ---
        if not search_results:
            # Provide more context in the "not found" message
            filters_used = [p for p in query_parts if p != base_query.strip()] # Show filters applied
            filters_str = f" with filters: [{', '.join(filters_used)}]" if filters_used else ""
            return f"No items found matching your criteria: '{base_query}'{filters_str}."

        output_results = []
        for item in search_results:
            # Safely get dates and format them back to YYYY-MM-DD HH:MM:S
            def format_timestamp(timestamp_ms):
                 if not timestamp_ms: return None
                 try:
                     # Convert milliseconds to seconds
                     timestamp_sec = timestamp_ms / 1000
                     return datetime.fromtimestamp(timestamp_sec).strftime('%Y-%m-%d %H:%M:%S')
                 except Exception:
                     return None # Handle potential errors during conversion

            created_str = format_timestamp(item.created)
            # modified_str = format_timestamp(item.modified) # Removed

            output_results.append({
                "title": item.title,
                "id": item.id,
                "type": item.type,
                "owner": item.owner,
                "snippet": item.snippet,
                # "description": item.description, # Include description
                "tags": item.tags,
                "typeKeywords": getattr(item, 'typeKeywords', None), # Include typeKeywords if available
                "created": created_str,
                "access": item.access, # Include access level
                "url": item.url # Include item URL
            })

        return json.dumps(output_results, indent=2)

    except ValueError as ve: # Catch validation errors specifically
        return f"Input validation error: {str(ve)}"
    except Exception as e:
        # Log the full traceback for better debugging if possible in the environment
        # traceback.print_exc()
        return f"An unexpected error occurred during ArcGIS content search: {str(e)}"


@tool
def summary_statistics(
    in_table: str,
    out_table: str,
    statistics_fields: Union[List[List[str]], str],
    case_field: Optional[Union[str, List[str]]] = None
) -> str:
    """Calculates summary statistics for fields in a table or feature class.

    This tool summarizes attribute values from an input table or feature class and writes the results
    to a new standalone table. It can calculate various statistics like sum, mean, min, max, standard deviation, etc.
    Optionally, statistics can be calculated for unique cases based on one or more grouping fields (case fields).

    GIS Concepts:
    - Attribute Tables: Data associated with geographic features or standalone tabular data.
    - Summary Statistics: Aggregated values (like sum, average) calculated from attribute fields.
    - Grouping (Case Field): Calculating statistics separately for each unique value or combination of values in specified fields.
    - Output Table: A new table created to store the calculated summary statistics.

    Args:
        in_table (str): The path to the input table or feature class containing the fields to summarize.
                        Must be an existing table or feature class.
        out_table (str): The path where the output summary statistics table will be saved.
                         Will be overwritten if it already exists.
        statistics_fields (Union[List[List[str]], str]): Specifies the statistics to calculate.
            Can be provided as:
            1. A list of lists/tuples: e.g., [['Population', 'SUM'], ['Area_KM', 'MEAN']]
            2. A semicolon-delimited string: e.g., "Population SUM;Area_KM MEAN"
            Valid statistic types: SUM, MEAN, MIN, MAX, RANGE, STD (Standard Deviation),
            COUNT, FIRST, LAST, MEDIAN, VARIANCE. Field names must exist in the input table.
        case_field (Optional[Union[str, List[str]]]): Field(s) used to group statistics (optional).
            If provided, statistics are calculated for each unique value (or combination of values)
            in these fields. Can be a single field name or a list of field names.
            Case fields must exist in the input table. Default is None (no grouping).

    Returns:
        str: A message indicating success or failure, including the path to the output table or error details.

    Example:
        >>> # Calculate total population and average area per state
        >>> summary_statistics(
        ...     in_table="D:/data/counties.shp",
        ...     out_table="D:/output/state_summary.dbf",
        ...     statistics_fields=[['Population', 'SUM'], ['Shape_Area', 'MEAN']],
        ...     case_field="State_Name"
        ... )
        "Successfully calculated summary statistics and saved to D:/output/state_summary.dbf."

        >>> # Calculate overall min and max elevation from a points table
        >>> summary_statistics(
        ...     in_table="D:/data/elevation_points.gdb/points",
        ...     out_table="D:/output/elevation_stats.dbf",
        ...     statistics_fields="Elevation MIN;Elevation MAX"
        ... )
        "Successfully calculated summary statistics and saved to D:/output/elevation_stats.dbf."

    Notes:
        - The input table/feature class must exist.
        - Field names used in `statistics_fields` and `case_field` must be valid fields in the input table.
        - The output table will be overwritten if it exists.
        - Ensure statistic types are valid (e.g., 'SUM', 'MEAN').
    """
    try:
        # Validate input table existence
        if not _dataset_exists(in_table):
            return f"Error: Input table/feature class '{in_table}' does not exist."

        # Validate statistics_fields format and content
        valid_stat_types = {"SUM", "MEAN", "MIN", "MAX", "RANGE", "STD", "COUNT", "FIRST", "LAST", "MEDIAN", "VARIANCE"}
        formatted_stats = []
        if isinstance(statistics_fields, str):
            # Parse semicolon-delimited string
            pairs = statistics_fields.split(';')
            for pair in pairs:
                parts = pair.strip().split()
                if len(parts) == 2:
                    field, stat_type = parts
                    if not _is_valid_field_name(in_table, field):
                         return f"Error: Field '{field}' in statistics_fields does not exist in '{in_table}'."
                    if stat_type.upper() not in valid_stat_types:
                        return f"Error: Invalid statistic type '{stat_type}'. Valid types are: {', '.join(valid_stat_types)}"
                    formatted_stats.append([field, stat_type.upper()])
                else:
                    return f"Error: Invalid format in statistics_fields string: '{pair}'. Expected 'FieldName StatType'."
            if not formatted_stats:
                 return "Error: statistics_fields string is empty or invalid."
        elif isinstance(statistics_fields, list):
            # Validate list of lists/tuples
            if not statistics_fields:
                 return "Error: statistics_fields list cannot be empty."
            for item in statistics_fields:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    field, stat_type = item
                    if not isinstance(field, str) or not isinstance(stat_type, str):
                         return f"Error: Invalid item format in statistics_fields list: {item}. Both elements must be strings."
                    if not _is_valid_field_name(in_table, field):
                         return f"Error: Field '{field}' in statistics_fields does not exist in '{in_table}'."
                    if stat_type.upper() not in valid_stat_types:
                        return f"Error: Invalid statistic type '{stat_type}'. Valid types are: {', '.join(valid_stat_types)}"
                    formatted_stats.append([field, stat_type.upper()])
                else:
                    return f"Error: Invalid item format in statistics_fields list: {item}. Expected ['FieldName', 'StatType'] or ('FieldName', 'StatType')."
        else:
            return "Error: statistics_fields must be a list of lists/tuples or a semicolon-delimited string."

        # Validate case_field(s) existence if provided
        formatted_case_fields = []
        if case_field:
            if isinstance(case_field, str):
                if not _is_valid_field_name(in_table, case_field):
                    return f"Error: Case field '{case_field}' does not exist in '{in_table}'."
                formatted_case_fields = [case_field]
            elif isinstance(case_field, list):
                if not case_field:
                     return "Error: case_field list cannot be empty if provided."
                for field in case_field:
                    if not isinstance(field, str):
                         return f"Error: Invalid item in case_field list: {field}. All items must be strings."
                    if not _is_valid_field_name(in_table, field):
                        return f"Error: Case field '{field}' does not exist in '{in_table}'."
                    formatted_case_fields.append(field)
            else:
                return "Error: case_field must be a string or a list of strings."

        # Execute the Statistics tool
        arcpy.analysis.Statistics(
            in_table=in_table,
            out_table=out_table,
            statistics_fields=formatted_stats,
            case_field=formatted_case_fields if formatted_case_fields else None # Pass None if empty list
        )
        return f"Successfully calculated summary statistics and saved to '{out_table}'."

    except arcpy.ExecuteError:
        # Return detailed geoprocessing error messages
        error_messages = arcpy.GetMessages(2) # 0=info, 1=warning, 2=error
        return f"ArcPy Error calculating statistics: {error_messages}"
    except Exception as e:
        # Catch any other unexpected errors
        return f"An unexpected error occurred: {str(e)}\n{traceback.format_exc()}"


@tool
def view_attribute_table_rows(
    in_table: str,
    num_rows: int = 5,
    fields: Optional[Union[str, List[str]]] = "*"
) -> str:
    """Displays the first N rows of an attribute table for a feature class or standalone table.

    This tool provides a quick preview of the attribute data by fetching and displaying
    a specified number of rows from the beginning of the table. It helps in understanding
    the table structure and content without loading the entire dataset.

    GIS Concepts:
    - Attribute Table: Tabular data associated with geographic features or standalone data.
    - Search Cursor: An ArcPy data access object used to iterate through rows in a table.
    - Fields: Columns in the attribute table.

    Args:
        in_table (str): The path to the input feature class or standalone table.
                        Must be an existing dataset.
        num_rows (int): The maximum number of rows to display. Defaults to 5.
                        Must be a positive integer.
        fields (Optional[Union[str, List[str]]]): The field(s) to include in the output.
            Can be a list of field names (e.g., ['FID', 'Name', 'Population']),
            a comma-separated string (e.g., "FID,Name,Population"), or "*" to include all fields.
            Defaults to "*". Field names must be valid for the input table.

    Returns:
        str: A string representation of the first N rows (up to num_rows), including field names
             and row values, or an error message if the operation fails.
             Output format is a simple text table.

    Example:
        >>> view_attribute_table_rows("D:/data/cities.shp", num_rows=3)
        "Field Names: ['FID', 'Shape', 'Name', 'Population']\\nRow 1: [0, 'Point', 'City A', 10000]\\nRow 2: [1, 'Point', 'City B', 25000]\\nRow 3: [2, 'Point', 'City C', 15000]"

        >>> view_attribute_table_rows("D:/data/parcels.gdb/land_parcels", num_rows=2, fields="ParcelID,Owner")
        "Field Names: ['ParcelID', 'Owner']\\nRow 1: ['APN001', 'Smith J']\\nRow 2: ['APN002', 'Doe A']"

    Notes:
        - The input table/feature class must exist.
        - If `fields` is specified, the field names must exist in the input table.
        - The number of rows returned might be less than `num_rows` if the table has fewer rows.
        - Geometry fields might display as their object type (e.g., 'Point', 'Polygon').
    """
    try:
        # Validate input table existence
        if not _dataset_exists(in_table):
            return f"Error: Input table/feature class '{in_table}' does not exist."

        # Validate num_rows
        if not isinstance(num_rows, int) or num_rows <= 0:
            return f"Error: num_rows must be a positive integer. Got: {num_rows}"

        # Validate and format fields parameter
        field_list = []
        all_fields_info = arcpy.ListFields(in_table)
        all_field_names = [f.name for f in all_fields_info]

        if fields == "*":
            field_list = all_field_names
        elif isinstance(fields, str):
            field_list = [f.strip() for f in fields.split(',')]
        elif isinstance(fields, list):
            field_list = fields
        else:
            return f"Error: 'fields' parameter must be '*', a comma-separated string, or a list of strings. Got type: {type(fields)}"

        # Check if specified fields exist
        invalid_fields = [f for f in field_list if f not in all_field_names]
        if invalid_fields:
            return f"Error: The following specified fields do not exist in '{in_table}': {', '.join(invalid_fields)}"
        if not field_list:
             return f"Error: No valid fields specified or found for '{in_table}'."


        # Use SearchCursor to fetch rows
        output_lines = [f"Field Names: {field_list}"]
        row_count = 0
        # Use a try-except block specifically for the SearchCursor
        try:
            with arcpy.da.SearchCursor(in_table, field_list) as cursor:
                for i, row in enumerate(cursor):
                    if i >= num_rows:
                        break
                    # Convert row tuple to list of strings for consistent display
                    # Handle potential None values gracefully
                    row_values = [str(val) if val is not None else 'None' for val in row]
                    output_lines.append(f"Row {i + 1}: {row_values}")
                    row_count += 1
        except RuntimeError as e:
             # Catch potential errors like field not found during cursor creation
             return f"Error accessing data in '{in_table}': {str(e)}"


        if row_count == 0:
            return f"Table '{in_table}' appears to be empty or no rows matched."

        return "\n".join(output_lines)

    except arcpy.ExecuteError:
        # General ArcPy errors
        error_messages = arcpy.GetMessages(2)
        return f"ArcPy Error viewing table rows: {error_messages}"
    except Exception as e:
        # Catch any other unexpected errors
        return f"An unexpected error occurred: {str(e)}\n{traceback.format_exc()}"


# Update __all__ to include the new tools
__all__ = [
    'add_field','append_features','aspect','buffer_features',
    'calculate_field','calculate_ndvi','calculate_savi','calculate_tpi',
    'clip_features','create_feature_class', 'define_projection','delete_features',
    'dissolve_features','download_landsat_tool','erase_features',
    'extract_by_mask','scan_workspace_directory_for_gis_files','hillshade','intersect_features',
    'list_fields','merge_features','project_features',
    'raster_calculator','reclassify_raster', 'search_arcgis_online_content',
    'select_features','slope', 'spatial_join',
    'union_features','zonal_statistics_as_table', 'scan_external_directory_for_gis_files',
    'summary_statistics', 'view_attribute_table_rows'
]