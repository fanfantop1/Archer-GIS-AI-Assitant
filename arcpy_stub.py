"""
arcpy compatibility stub for Linux/macOS.

Replaces ArcGIS Pro's arcpy with open-source equivalents (geopandas, rasterio,
shapely) for basic operations, and raises NotImplementedError for ArcGIS-specific
features that require a licensed ArcGIS Pro installation.

Usage (in each file that needs arcpy):
    try:
        import arcpy
    except ModuleNotFoundError:
        import arcpy_stub as arcpy
"""

import os
import warnings

# --- Try to import OSS GIS libraries ---
try:
    import geopandas as gpd
    import pandas as pd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    import rasterio as _rasterio
    from rasterio import features as _rasterio_features
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from shapely.geometry import shape, box, Point, mapping
    from shapely import wkt
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    import fiona
    HAS_FIONA = True
except ImportError:
    HAS_FIONA = False

try:
    from osgeo import ogr, osr, gdal
    HAS_GDAL = True
except ImportError:
    HAS_GDAL = False


# ============================================================
# Exceptions
# ============================================================

class ExecuteError(Exception):
    """Mimics arcpy.ExecuteError."""
    def __init__(self, messages=""):
        self.messages = messages
        super().__init__(messages)


# ============================================================
# env
# ============================================================

class _Env:
    """Mimics arcpy.env environment settings."""
    def __init__(self):
        self._workspace = None
        self._overwriteOutput = True

    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, value):
        if value is not None and not os.path.isdir(value):
            warnings.warn(f"Workspace does not exist: {value}")
        self._workspace = value

    @property
    def overwriteOutput(self):
        return self._overwriteOutput

    @overwriteOutput.setter
    def overwriteOutput(self, value):
        self._overwriteOutput = bool(value)

env = _Env()


# ============================================================
# Product info
# ============================================================

def ProductInfo():
    """Return a dummy product info string."""
    return "Licensed"  # Pretend we have a license


# ============================================================
# Exists
# ============================================================

def Exists(path):
    """Check if a dataset, feature class, or file exists."""
    if path is None:
        return False
    if os.path.exists(path):
        return True
    # Check if it's in the workspace as a named dataset
    ws = env.workspace
    if ws:
        full_path = os.path.join(ws, path)
        if os.path.exists(full_path):
            return True
        # Try common GIS extensions
        for ext in ['.shp', '.tif', '.gpkg', '.geojson']:
            if os.path.exists(full_path + ext):
                return True
    return False


# ============================================================
# Describe
# ============================================================

class _DescribeResult:
    """Mimics arcpy.Describe result."""
    def __init__(self, path):
        self._path = path
        self._catalogPath = path
        self._name = os.path.basename(path)
        self._extension = os.path.splitext(path)[1]

        # Detect type
        if os.path.isdir(path):
            self._dataType = "Folder"
            self._workspaceType = "FileSystem"
        elif self._extension.lower() in ('.shp',):
            self._dataType = "ShapeFile"
            self._shapeType = "Polygon"
        elif self._extension.lower() in ('.tif', '.tiff'):
            self._dataType = "RasterDataset"
        elif self._extension.lower() in ('.gpkg',):
            self._dataType = "Workspace"
        else:
            self._dataType = "FeatureClass"

        # Try to get more info via geopandas
        if HAS_GEOPANDAS:
            try:
                if self._extension.lower() in ('.shp', '.gpkg', '.geojson'):
                    gdf = gpd.read_file(path)
                    geom_types = gdf.geometry.type.unique()
                    if len(geom_types) == 1:
                        self._shapeType = geom_types[0]
                    else:
                        self._shapeType = "Mixed"
                    if gdf.crs:
                        self._spatialReference = _SpatialReference(gdf.crs.to_wkt() if hasattr(gdf.crs, 'to_wkt') else str(gdf.crs))
            except Exception:
                pass

    @property
    def dataType(self):
        return self._dataType

    @property
    def datasetType(self):
        return self._dataType

    @property
    def shapeType(self):
        return getattr(self, '_shapeType', 'Unknown')

    @property
    def spatialReference(self):
        return getattr(self, '_spatialReference', _SpatialReference("Unknown"))

    @property
    def catalogPath(self):
        return self._catalogPath

    @property
    def name(self):
        return self._name

    @property
    def extension(self):
        return self._extension

    @property
    def workspaceType(self):
        return getattr(self, '_workspaceType', 'FileSystem')

    @property
    def filePath(self):
        return self._path


def Describe(path):
    """Describe a dataset."""
    if not path:
        raise ValueError("Input path is None or empty")
    return _DescribeResult(path)


# ============================================================
# SpatialReference
# ============================================================

class _SpatialReference:
    """Mimics arcpy.SpatialReference."""
    def __init__(self, value=None):
        self._name = "Unknown"
        self._wkt = ""
        if value is None:
            value = 4326  # Default to WGS84
        if isinstance(value, int):
            # EPSG code
            self._name = f"GCS_WGS_1984" if value == 4326 else f"EPSG:{value}"
            if HAS_GDAL:
                srs = osr.SpatialReference()
                srs.ImportFromEPSG(value)
                self._wkt = srs.ExportToWkt()
        elif isinstance(value, str):
            self._name = value
            self._wkt = value

    @property
    def name(self):
        return self._name

    @property
    def wkt(self):
        return self._wkt

    def __str__(self):
        return self._name


def SpatialReference(value=None):
    return _SpatialReference(value)


# ============================================================
# ListFields
# ============================================================

class _Field:
    """Mimics arcpy.Field."""
    def __init__(self, name, field_type="String", length=255):
        self.name = name
        self.type = field_type
        self.length = length
        self.aliasName = name

    def __repr__(self):
        return f"<Field: {self.name} ({self.type})>"


def ListFields(dataset, wild_card=None):
    """List fields of a dataset using geopandas or fiona."""
    fields = []

    if HAS_GEOPANDAS:
        try:
            if isinstance(dataset, str):
                gdf = gpd.read_file(dataset, rows=1)
            else:
                gdf = dataset
            dtypes = gdf.dtypes
            for col in dtypes.index:
                if wild_card and wild_card != "*":
                    import fnmatch
                    if not fnmatch.fnmatch(col, wild_card):
                        continue
                dt = str(dtypes[col])
                if 'int' in dt:
                    ft = 'Integer'
                elif 'float' in dt:
                    ft = 'Double'
                elif 'datetime' in dt:
                    ft = 'Date'
                else:
                    ft = 'String'
                fields.append(_Field(col, ft))
            return fields
        except Exception:
            pass

    # Fallback: try fiona
    if HAS_FIONA:
        try:
            with fiona.open(dataset) as src:
                schema = src.schema
                for name, ft in schema['properties'].items():
                    if wild_card and wild_card != "*":
                        import fnmatch
                        if not fnmatch.fnmatch(name, wild_card):
                            continue
                    if 'int' in ft:
                        ft = 'Integer'
                    elif 'float' in ft:
                        ft = 'Double'
                    else:
                        ft = 'String'
                    fields.append(_Field(name, ft))
                return fields
        except Exception:
            pass

    return fields


# ============================================================
# ListFeatureClasses / ListDatasets / ListRasters / ListTables
# ============================================================

def _list_in_workspace(ws, extensions, wild_card=None):
    """Generic workspace lister."""
    results = []
    if not ws or not os.path.isdir(ws):
        return results

    import fnmatch
    for f in os.listdir(ws):
        full = os.path.join(ws, f)
        ext = os.path.splitext(f)[1].lower()
        if ext in extensions:
            if wild_card and wild_card != "*":
                if not fnmatch.fnmatch(f, wild_card):
                    continue
            results.append(f)
    return results


def ListFeatureClasses(wild_card=None):
    """List feature classes in the workspace."""
    return _list_in_workspace(env.workspace, ['.shp', '.gpkg', '.geojson'], wild_card)


def ListDatasets(wild_card=None):
    """List datasets in the workspace."""
    items = []
    ws = env.workspace
    if not ws or not os.path.isdir(ws):
        return items
    for d in os.listdir(ws):
        full = os.path.join(ws, d)
        if os.path.isdir(full) or d.endswith('.gdb'):
            items.append(d)
    return items


def ListRasters(wild_card=None):
    """List rasters in the workspace."""
    return _list_in_workspace(env.workspace, ['.tif', '.tiff', '.img', '.jpg', '.png'], wild_card)


def ListTables(wild_card=None):
    """List tables in the workspace."""
    return _list_in_workspace(env.workspace, ['.csv', '.dbf', '.xlsx', '.xls'], wild_card)


# ============================================================
# Raster
# ============================================================

class _Raster:
    """Mimics arcpy.Raster."""
    def __init__(self, path):
        self._path = path
        self._raster = None
        if HAS_RASTERIO:
            try:
                self._raster = _rasterio.open(path)
            except Exception:
                pass

    @property
    def width(self):
        if self._raster:
            return self._raster.width
        return 0

    @property
    def height(self):
        if self._raster:
            return self._raster.height
        return 0

    @property
    def meanCellHeight(self):
        if self._raster:
            return self._raster.res[0]
        return 0

    @property
    def meanCellWidth(self):
        if self._raster:
            return self._raster.res[1]
        return 0

    @property
    def bandCount(self):
        if self._raster:
            return self._raster.count
        return 0

    def __str__(self):
        return self._path


def Raster(path):
    """Create a Raster object."""
    if not os.path.exists(path):
        raise RuntimeError(f"Raster not found: {path}")
    return _Raster(path)


# ============================================================
# da.SearchCursor
# ============================================================

class da:
    """Data access module stub."""

    class SearchCursor:
        """Mimics arcpy.da.SearchCursor using geopandas."""
        def __init__(self, dataset, field_names):
            self.dataset = dataset
            self.field_names = [f if isinstance(f, str) else f.name for f in field_names]
            self._data = None
            self._idx = 0
            if HAS_GEOPANDAS:
                try:
                    gdf = gpd.read_file(dataset)
                    cols = [c for c in self.field_names if c in gdf.columns or c == '*']
                    if '*' in self.field_names:
                        cols = list(gdf.columns)
                    self._data = gdf[cols].values.tolist()
                except Exception:
                    self._data = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __iter__(self):
            return iter(self._data or [])

        def __len__(self):
            return len(self._data or [])


# ============================================================
# GetMessages / GetCount_management
# ============================================================

_last_messages = ""

def GetMessages(severity=0):
    """Return last error/warning messages."""
    return _last_messages


def GetCount_management(dataset):
    """Return feature count using geopandas."""
    if HAS_GEOPANDAS:
        try:
            gdf = gpd.read_file(dataset)
            return [len(gdf)]
        except Exception:
            pass
    return [0]


# ============================================================
# CheckInExtension / CheckOutExtension
# ============================================================

def CheckOutExtension(name):
    """Stub - no license needed on Linux."""
    return "CheckedOut"


def CheckInExtension(name):
    """Stub."""
    return "CheckedIn"


# ============================================================
# NOT IMPLEMENTED operations
# ============================================================

def _not_implemented(name):
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"arcpy.{name}() requires ArcGIS Pro (Windows-only). "
            f"This operation is not available on Linux."
        )
        return None
    return wrapper


class _NotImplModule:
    """Module that returns NotImplementedError wrappers for any attribute access."""
    def __getattr__(self, name):
        return _not_implemented(f"<module>.{name}")


class _AnalysisModule:
    """Stub for arcpy.analysis tools."""
    @staticmethod
    def Buffer(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Buffer requires ArcGIS Pro. Use geopandas/shapely instead.")

    @staticmethod
    def Clip(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Clip requires ArcGIS Pro. Use geopandas instead.")

    @staticmethod
    def Intersect(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Intersect requires ArcGIS Pro.")

    @staticmethod
    def Select(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Select requires ArcGIS Pro.")

    @staticmethod
    def SpatialJoin(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.SpatialJoin requires ArcGIS Pro.")

    @staticmethod
    def Statistics(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Statistics requires ArcGIS Pro.")

    @staticmethod
    def Union(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Union requires ArcGIS Pro.")

    @staticmethod
    def Erase(*args, **kwargs):
        raise NotImplementedError("arcpy.analysis.Erase requires ArcGIS Pro.")


class _ManagementModule:
    """Stub for arcpy.management tools."""
    @staticmethod
    def Delete(*args, **kwargs):
        path = args[0] if args else kwargs.get('input_features', '')
        if os.path.exists(path):
            os.remove(path)
            return f"Deleted: {path}"
        return f"Nothing to delete: {path}"

    @staticmethod
    def CreateFeatureclass(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CreateFeatureclass requires ArcGIS Pro.")

    @staticmethod
    def CreateFeatureDataset(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CreateFeatureDataset requires ArcGIS Pro.")

    @staticmethod
    def CreateFileGDB(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CreateFileGDB requires ArcGIS Pro.")

    @staticmethod
    def Append(*args, **kwargs):
        raise NotImplementedError("arcpy.management.Append requires ArcGIS Pro.")

    @staticmethod
    def Merge(*args, **kwargs):
        raise NotImplementedError("arcpy.management.Merge requires ArcGIS Pro.")

    @staticmethod
    def Dissolve(*args, **kwargs):
        raise NotImplementedError("arcpy.management.Dissolve requires ArcGIS Pro.")

    @staticmethod
    def Project(*args, **kwargs):
        raise NotImplementedError("arcpy.management.Project requires ArcGIS Pro.")

    @staticmethod
    def DefineProjection(*args, **kwargs):
        raise NotImplementedError("arcpy.management.DefineProjection requires ArcGIS Pro.")

    @staticmethod
    def AddField(*args, **kwargs):
        raise NotImplementedError("arcpy.management.AddField requires ArcGIS Pro.")

    @staticmethod
    def CalculateField(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CalculateField requires ArcGIS Pro.")

    @staticmethod
    def CopyFeatures(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CopyFeatures requires ArcGIS Pro.")

    @staticmethod
    def CopyRows(*args, **kwargs):
        raise NotImplementedError("arcpy.management.CopyRows requires ArcGIS Pro.")

    @staticmethod
    def JoinField(*args, **kwargs):
        raise NotImplementedError("arcpy.management.JoinField requires ArcGIS Pro.")

    @staticmethod
    def RepairGeometry(*args, **kwargs):
        raise NotImplementedError("arcpy.management.RepairGeometry requires ArcGIS Pro.")

    @staticmethod
    def TableToTable(*args, **kwargs):
        raise NotImplementedError("arcpy.management.TableToTable requires ArcGIS Pro.")

    @staticmethod
    def XYTableToPoint(*args, **kwargs):
        raise NotImplementedError("arcpy.management.XYTableToPoint requires ArcGIS Pro.")


class _SA_Module:
    """Stub for arcpy.sa (Spatial Analyst) tools."""
    @staticmethod
    def __getattr__(name):
        return _not_implemented(f"sa.{name}")


class _ConversionModule:
    """Stub for arcpy.conversion tools."""
    @staticmethod
    def TableToTable(*args, **kwargs):
        raise NotImplementedError("arcpy.conversion.TableToTable requires ArcGIS Pro.")


# ============================================================
# Module-level attribute assignments
# ============================================================

analysis = _AnalysisModule()
management = _ManagementModule()
sa = _SA_Module()
conversion = _ConversionModule()
nax = _NotImplModule()
stats = _NotImplModule()

# Assign nested module stubs
da = da  # Use the class defined above


# ============================================================
# Cleanup
# ============================================================

# Silence the deprecation warning about google.generativeai from langchain_google_genai
warnings.filterwarnings(
    "ignore",
    message=".*google\\.generativeai.*package has ended.*"
)
