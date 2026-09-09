import pathlib
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt


def generate_report_from_filenames(path, race_name='not defined', close_figures=True):
    """
    Generate a report from a list of filenames.

    Parameters
    ----------
    path : str
        e.g., ./path/to_folder/*.log
    race_name : str, optional
        name of the race, by default 'not defined'
    
    Returns
    -------
    None
    """
    from .read_log_files import read_mflog

    assert path.endswith('*.log'), 'path end with *.log'
    
    df = read_mflog(path).sort_index()
    generate_report_from_dataframe(df, path, race_name, close_figures=close_figures)


def generate_report_from_dataframe(df, path, race_name='not defined', close_figures=True):

    """
    Generate a report from a list of filenames. Report will be saved in the same folder as the data.

    Parameters
    ----------
    df : pd.DataFrame
        dataframe with columns 'lat', 'lon', 'co2', 'watertemp', 'salinity'
    path : str
        e.g., ./path/to_folder/*.log
    race_name : str, optional
        name of the race, by default 'not defined'
    
    Returns
    -------
    None
    """

    df = df.sort_index()

    readme_text = make_summary_text(df, path, race_name=race_name)

    fig_maps, ax = plot_global_and_zoomed_in_maps(df, path)
    fig_ts, ax = plot_time_series_triplet(df, path)
    fig_text, ax = create_figure_from_text(readme_text)

    report_path = make_report_name(path)

    print('writing report to ', report_path)
    write_figs_to_pdf([fig_text, fig_maps, fig_ts], report_path, dpi=150)

    if close_figures:
        plt.close("all")


def make_report_name(path):
    """
    Make a name for the report based on the folder name.
    """
    from glob import glob
    import pathlib

    flist = glob(str(path))
    if len(flist) == 0:
        raise FileNotFoundError(f'no files found in {path}')
    elif len(flist) == 1:
        ppath = pathlib.Path(flist[0])
    else:
        ppath = pathlib.Path(flist[0]).parent

    # if path name has an extension, remove it
    name = ppath.name
    if '.' in name[-5:]:
        name = ".".join(name.split('.')[:-1])
    parent_and_name = ppath.parent / (name + '_report.pdf')

    return parent_and_name


def plot_global_map_of_cruise_track(lat: pd.Series, lon: pd.Series, time: pd.DatetimeIndex, ax=None, global_extent: bool=True, **kwargs):
    """
    Make a map to show where in the world the cruise track went.

    Parameters
    ----------
    lat : pd.Series
        Latitude values.
    lon : pd.Series
        Longitude values.
    """
    # use cartopy to plot the cruise track
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    mask = (lat != 0) & (lon != 0)
    lat = lat[mask]
    lon = lon[mask]
    time_since_start = (time - time[0]).astype('timedelta64[s]').values[mask]

    # make a map
    if ax is None:
        fig = plt.figure(figsize=(8, 4))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    else:
        fig = plt.gcf()

    ax._autoscaleXon = True
    ax._autoscaleYon = True

    if global_extent:
        ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())

    # add land and coastlines
    ax.add_feature(cfeature.LAND, facecolor='#cccccc')
    ax.coastlines(lw=0.5)

    # add the cruise track
    ax.scatter(lon, lat, s=3, c=time_since_start, transform=ccrs.PlateCarree(), rasterized=True, **kwargs)

    return fig, ax


def plot_global_and_zoomed_in_maps(df: pd.DataFrame, path):
    """
    Make a map to show where in the world the cruise track went.

    Parameters
    ----------
    lat : pd.Series
        Latitude values.
    lon : pd.Series
        Longitude values.
    
    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """

    import cartopy.crs as ccrs

    lat = df['lat']
    lon = df['lon']
    time = df.index

    cmap = plt.cm.Spectral_r

    path = pathlib.Path(path)

    fig, ax = plt.subplots(2, 1, figsize=(8, 8), subplot_kw={'projection': ccrs.PlateCarree()}, dpi=150)

    plot_global_map_of_cruise_track(lat, lon, time, ax=ax[0], cmap=cmap)
    plot_global_map_of_cruise_track(lat, lon, time, ax=ax[1], cmap=cmap, global_extent=False)

    t0 = time[0]
    t1 = time[-1]
    ax[1].set_title(f'start: {t0:%Y-%m-%d}', color=cmap(0.1), weight='bold', loc='left')
    ax[1].set_title(f'end: {t1:%Y-%m-%d}',   color=cmap(0.9), weight='bold', loc='right')

    fig.tight_layout()

    # p0 = ax[0].get_position()
    # p1 = ax[1].get_position()
    # a1 = ax[1].get_data_ratio()
    # new_height = p0.width * a1

    # ax[1].set_position([p0.x0, p0.y0 - new_height - 0.05, p0.width, new_height])

    title = f'{path.parent.name}:   {t0:%Y-%m-%d} — {t1:%Y-%m-%d}'
    fig.suptitle(title, weight='bold', y=1.02, size='large')

    for a in ax:
        a._autoscaleXon = False
        a._autoscaleYon = False

    return fig, ax


def plot_time_series_triplet(df, path):

    path = pathlib.Path(path)

    fig, ax = plt.subplots(3, 1, figsize=(8, 7), sharex=True, dpi=150)
    df.co2.where(lambda x: (x > 200) & (x < 800)).plot(marker='.', lw=0, ms=2, ax=ax[0], rasterized=True)
    df.watertemp.plot(marker='.', lw=0, ms=2, ax=ax[1], color='C1', rasterized=True)
    df.salinity.plot(marker='.', lw=0, ms=2, ax=ax[2], color='C2', rasterized=True)

    ax[0].set_ylabel('xCO$_2$ [ppm]')
    ax[1].set_ylabel('Temperature [°C]')
    ax[2].set_ylabel('Salinity [PSU]')

    ax[-1].set_xlabel('Time [UTC]')

    ax[0].set_title('xCO$_2$', loc='left', weight='bold')
    ax[1].set_title('Water Temperature', loc='left', weight='bold')
    ax[2].set_title('Salinity', loc='left', weight='bold')

    t0 = df.index[0]
    t1 = df.index[-1]

    fig.tight_layout()

    title = f'{path.parent.name}:   {t0:%Y-%m-%d} — {t1:%Y-%m-%d}'
    fig.suptitle(title, weight='bold', y=1.02, size='large')

    return fig, ax


def get_ocean_or_sea_name(lat, lon, shape_file_name):
    from shapely.geometry import Point
    import geopandas as gpd

    # read in shapefile
    oceans = gpd.read_file(shape_file_name)
    # use geopandas to test if a point is in a polygon
    points = gpd.GeoDataFrame(np.c_[lat, lon], columns=['lat', 'lon'])
    points['geometry'] = points.apply(lambda row: Point(row.lon, row.lat), axis=1)
    points = points.set_geometry('geometry')
    points.crs = 'EPSG:4326'
    
    points.to_crs(oceans.crs, inplace=True)

    # set a crs for points using .to_crs() method
    points.to_crs('EPSG:4326', inplace=True)

    # Perform a spatial join
    joined = gpd.sjoin(points, oceans, how='left', op='within')

    # Get the name of the ocean or sea
    regions = joined.set_index(['lat', 'lon']).NAME

    return regions


def dedent(text):
    lines = text.split('\n')

    for line in lines:
        if line.strip() == '':
            continue
        else:
            line0 = line
            break
    
    # count spaces at beginning of first line
    n = len(line0) - len(line0.lstrip())
    for i, line in enumerate(lines):
        lines[i] = line[n:]

    return '\n'.join(lines)


def get_regions_visited_as_text(lat, lon):
    scripts_dir = pathlib.Path(__file__).parent.absolute().resolve()
    shape_file_name = scripts_dir / 'world_seas_IHO/World_Seas.shp'

    if not shape_file_name.exists():
        return [
            f"Wold Seas IHO shapefile not found ({shape_file_name})", 
            "download from https://www.marineregions.org/downloads.php#iho",
            "place in `CO2yacht/scripts/wold_seas_IHO` "]
    else:
        regions = get_ocean_or_sea_name(lat, lon, shape_file_name)
        regions_visited = regions.value_counts().to_dict()
        regions_text = [f"{k+':': <23} {v: >6}" for k, v in regions_visited.items()]
        return regions_text


def make_summary_text(df, path, race_name='not defined'):
    import pathlib
    from glob import glob

    ppath = pathlib.Path(path)
    flist = list(glob(path))
    spacing = "\n" + " " * 12  # 12 because indent in 'text' below is 8 spaces + 4 spaces for '    '

    fnames = spacing.join([pathlib.Path(f).name for f in flist][:5])
    if len(flist) > 10:
        fnames += f"{spacing}...{spacing}more than 5 files in folder"

    # mask the bad lats and lons
    mask = (df['lat'] != 0) & (df['lon'] != 0)
    df = df.where(mask).dropna(how='all')

    lat = df['lat']
    lon = df['lon']
    time = df.index

    max_allowed_gap = 60 * 5
    sampling_interval_seconds = time.to_series().diff().iloc[1:].astype('timedelta64[s]').astype('int')
    sampling_time_minutes = sampling_interval_seconds.sum() / 60
    gaps_mins = sampling_interval_seconds.where(lambda x: x > max_allowed_gap).sum() / 60
    percent_missing_data = gaps_mins / sampling_time_minutes * 100

    regions_text = spacing.join(get_regions_visited_as_text(lat, lon))

    text = dedent(f"""
        AUTO-GENERATED METADATA
        =======================

        PLATFORM INFO
        =============
        vessel_type:  yacht IMOCA 60 class 
        vessel_name:  OLIVER HEER OCEAN RACING
        race_name:    {race_name}
        instrument:   SubCtech OceanPack Race
        co2_sensor:   LI850
        ctd_sensor:   CTD48-1892  
        meteo_sensor: PTB10_Barometer-U0250319

        
        FILES
        =====
        parent_folder: {ppath.parent.name}
        number_files:  {len(flist)}
        file_names:
            {fnames}


        GEOGRAPHICAL
        ============
        time_start:    {time.min()}
        time_stop:     {time.max()}
        num_days:      {(time.max() - time.min()).days}

        latitude_min:  {lat.min():.3f}
        latitude_max:  {lat.max():.3f}
        longitude_min: {lon.min():.3f}
        longitude_max: {lon.max():.3f}
        
        region_counts: 
            {regions_text}


        MEASUREMENTS
        ============
        number_measurements: {len(df)}
        total_sampling_time: {sampling_time_minutes:.1f} mins
        gaps_longer_than_5min: {gaps_mins:.1f} mins
        percent_missing_data: {percent_missing_data:.1f} %
        """)

    return text


def create_figure_from_text(text, **kwargs):
    """
    Create a figure from a text string.
    """

    from matplotlib import pyplot as plt

    # default figsize is A4
    props = dict(figsize=(8.27, 11.69), dpi=150)
    props.update(kwargs)
    fig = plt.figure(**props)
    ax = fig.add_subplot(1, 1, 1)
    ax.text(0, 1, text, ha='left', va='top', transform=ax.transAxes, fontdict={'family': 'monospace'})
    ax.axis('off')

    return fig, ax


def write_figs_to_pdf(figs, path, **kwargs):
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        for fig in figs:
            pdf.savefig(fig, **kwargs)