# arcgis_search_tool.py
import arcpy
from arcgis.gis import GIS
import os
import json
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from dotenv import load_dotenv
from langchain.tools import tool

# Load environment variables from .env file
load_dotenv()

# --- Authentication Setup ---

ARCGIS_URL = "https://www.arcgis.com"
ARC_USER = os.environ.get("ARC_USER")
ARC_PASS = os.environ.get("ARC_PASS")
# Consider adding ARCGIS_API_KEY handling if needed for other auth methods
# ARCGIS_API_KEY = os.environ.get("ARCGIS_API_KEY")

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

# --- Tool Definition ---

@tool
def search_arcgis_content(
    query: str,
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
    search_outside_org: bool = True # Renamed from search_public
) -> str:
    """Searches ArcGIS Online/Portal for GIS items using advanced filtering based on the REST API query syntax.

    Allows flexible searching using keywords and various filters like title, item type, owner,
    tags, typeKeywords, description, snippet, created date, group ID,
    and categories. Constructs queries following ArcGIS REST API standards.
    Only use Feature Service, and Image Service item types for the search.
    Does NOT perform complex spatial filtering (like polygon intersects) during the item search itself;
    use location names in the 'query' argument for geographic focus.
    Results are sorted by relevance descending by default.

    Suggestions for improving search results:
    - Use specific keywords or phrases in the query (e.g., 'california population density').
    - Searching using the title and snippet fields often yields the best results if described properly.
    
    GIS Concepts:
    - Content Search: Finding GIS items based on metadata. Uses Lucene query syntax.
    - Item Metadata Fields: title, tags, snippet, description, type, typeKeywords, owner, created, id, access, categories, group.
    - Living Atlas Focus: Option to prioritize searching common Living Atlas sources if no specific owner/group/tags are given.

    Args:
        query: The primary keyword search string (e.g., "california population density", "hospitals near main street london"). Can include boolean operators (AND, OR, NOT) and field searches (e.g., 'title:"San Francisco"').
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
    if not isinstance(query, str): # Allow empty query if other filters are used
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
        if query.strip():
             # Wrap base query in parentheses if it contains spaces or operators, to be safe
             if ' ' in query.strip() or any(op in query for op in [' AND ', ' OR ', ' NOT ']):
                 query_parts.append(f"({query.strip()})")
             else:
                 query_parts.append(query.strip())


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
            filters_used = [p for p in query_parts if p != query.strip()] # Show filters applied
            filters_str = f" with filters: [{', '.join(filters_used)}]" if filters_used else ""
            return f"No items found matching your criteria: '{query}'{filters_str}."

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
                "description": item.description, # Include description
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

# Example of how to potentially add the get_living_atlas_item_data tool if needed
# from less_tools import get_living_atlas_item_data

# You might want to define __all__ if this becomes a module others import from
# __all__ = ['search_arcgis_content', 'get_gis_connection'] # Add other tools if defined here