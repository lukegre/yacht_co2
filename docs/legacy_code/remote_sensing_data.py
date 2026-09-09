import xarray as xr
import pandas as pd


def get_remote_sensing_latest_week(today=pd.Timestamp.today()):
    
    sst = _get_latest_7days(get_sst, today)
    chl = _get_latest_7days(get_chl, today)
    
    return sst, chl


def _get_latest_7days(func, today):
    yesterday = today - pd.Timedelta('1D')
    last_week = yesterday - pd.Timedelta('6D')
    days = pd.date_range(last_week, yesterday, freq='1D')
    
    ds_all = []
    for date in days:
        try:
            ds_all += func(date),
        except:
            print(f'could not download data for {date:%Y-%m-%d}')
    
    ds_all = xr.concat(ds_all, 'time')
    return ds_all


def get_sss(dest='../data/SSS/'):
    url = (
        "ftp://nrt.cmems-du.eu/Core/"
        "/MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013/dataset-sss-ssd-nrt-weekly/"
        "/2022/dataset-sss-ssd-nrt-weekly_20221026T1200Z_P20221101T0000Z.nc")
    fname = download_cmems_data(url, dest_dir=dest)
    ds = xr.open_dataset(fname)
    sss = ds.sos.assign_coords(lon=lambda x: (x.lon - 180) % 360 - 180).sortby('lon')
    return sss


def get_sst(date, dest_dir='../data/SST/', source='noaa'):
    t= pd.to_datetime(date)
    if source == 'cmems':
        url = (
            "ftp://nrt.cmems-du.eu/Core/"
            "SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001/"
            "METOFFICE-GLO-SST-L4-NRT-OBS-ANOM-V2/"
            f"/{t:%Y}/{t:%m}/{t:%Y%m%d}120000-UKMO-L4_GHRSST-SSTfnd-OSTIAanom-GLOB-v02.0-fv02.0.nc")
    elif source == 'noaa':
        url = (
            "https://www.ncei.noaa.gov/data/"
            "sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr/"
            f"{t:%Y%m}/oisst-avhrr-v02r01.{t:%Y%m%d}.nc")
    else:
        raise ValueError('source can be `noaa` or `cmems`')
    
    fname = download_cmems_data(url, dest_dir=dest_dir)
    
    ds = xr.open_dataset(fname)
    if source == 'cmems':
        ds['sst'] = ds.analysed_sst - 273.15
        ds = ds.drop('analysed_sst')
    elif source == 'noaa': 
        ds = ds.isel(zlev=0).rename(anom='sst_anomaly')
    ds = ds.assign_coords(lon=lambda x: (x.lon - 180) % 360 - 180).sortby('lon')
    return ds


def get_chl(date, dest_dir='../data/CHL/'):
    t= pd.to_datetime(date)
    url = (
        "ftp://my.cmems-du.eu/Core/"
        "OCEANCOLOUR_GLO_BGC_L4_MY_009_104/"
        "cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D"
        f"/{t:%Y}/{t:%m}/{t:%Y%m%d}_cmems_obs-oc_glo_bgc-plankton_myint_l4-gapfree-multi-4km_P1D.nc")
    
    fname = download_cmems_data(url, dest_dir=dest_dir)
    ds = xr.open_dataset(fname).sortby('lat')
    ds = ds.assign_coords(lon=lambda x: (x.lon - 180) % 360 - 180).sortby('lon')
    return ds.CHL


def download_cmems_data(url, dest_dir='../data/'):
    import dotenv
    
    dotenv.load_dotenv()
    env = dotenv.dotenv_values()
    
    username = env['CMEMS_USER']
    password = env['CMEMS_PASS']
    
    fname = download_file(url, path=dest_dir, username=username, password=password)
    return fname
    

def download_file(
    url,
    path=".",
    fname=None,
    decompress=True,
    premission=774,
    username=None,
    password=None,
    verbosity=2,
    **kwargs,
):
    """
    A simple wrapper around the pooch package that makes downloading files easier

    Removes the need to set the hash of the file and the name is taken from the url.

    Parameters
    ----------
    url: str
        The url of the file to download
    path: str
        The destination to which the file will be downloaded. Must exist
        and must have write permission
    name: str | None
        By default [None], will get the file name from the url, or can be
        set to a string.
    decompress: bool [True]
        if the file name contains an extension that is a known compressed
        format, the file will automatically be decompressed and the
        decompressed files will be returned
    premission: int [774]
        The permission to set the download and all subfiles to.
        Must be three integer values for the file permissions - see chmod
        Does not accept four digit octal values.
        Note that permissions will be changed even if the files already exist.
    username: str | None
        if required for given url and protocol (e.g. FTP)
    password: str | None
        if required for given url and protocol (e.g. FTP)
    verbosity: int [25]
        the level of logging to use. Set to level
            0 = hide all logging
            1 = show file names that do not exist
            2 = show progress bar of files that do not exist
            3 = show progress bar and all files
            4 = show all logging - including pooch
    **kwargs: key-value
        any standard inputs of pooch

    Returns
    -------
    str | list:
        if only a single entry is downloaded / decompressed, then a string will
        be returned, otherwise, a list will be returned

    """
    from pathlib import Path as posixpath
    import pooch
    import logging
    import sys

    logger = pooch.get_logger()

    if "log_level" in kwargs:
        logger.warning("log_level is deprecated. Use verbosity instead.")
        verbosity = kwargs.pop("log_level", None)

    log_level = 24 - verbosity
    while len(logger.handlers) > 0:
        logger.removeHandler(logger.handlers[0])

    formatter = logging.Formatter("log-%(name)s | %(message)s")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)
    logger.addHandler(handler)

    if fname is None:
        fname = posixpath(url).name

    path = str(posixpath(path).expanduser().resolve())

    if decompress:
        decompressor = kwargs.get("processor", None)
        if decompressor is None:
            if ".zip" in url:
                kwargs["processor"] = pooch.processors.Unzip()
            elif ".tar" in url:
                kwargs["processor"] = pooch.processors.Untar()
            elif (".gz" in url) or (".bz2" in url) or (".xz" in url):
                kwargs["processor"] = pooch.processors.Decompress()

    downloader = kwargs.get("downloader", None)
    if downloader is None:
        downloader = pooch.downloaders.choose_downloader(url)
    if hasattr(downloader, "username") and username is not None:
        downloader.username = username
    if hasattr(downloader, "password") and password is not None:
        downloader.password = password

    # show the progress bar if the log level <= 20
    if log_level <= 22:
        downloader.progressbar = True
    kwargs["downloader"] = downloader

    props = dict(fname=fname, path=path)
    props.update(kwargs)

    fpath = posixpath(path).joinpath(fname)
    # if the file does not exist show if verbosity >= 25
    if fpath.is_file():
        logger.log(21, fname)
    else:
        logger.log(23, fname)
    # here we do the actual downloading
    flist = pooch.retrieve(url, None, **props)

    change_file_permissions(flist, premission)

    # return the string if it's the only item in the list
    if isinstance(flist, list):
        if len(flist) == 1:
            return flist[0]
    return flist


def change_file_permissions(path, permission=774):
    """
    Give group permission to a file or directory
    """
    import os
    from numpy import ndarray
    from pathlib import Path as posixpath

    perm = int(str(permission), base=8)

    if isinstance(path, str):
        if os.path.isfile(path):
            os.chmod(path, perm)
        else:
            for root, dirs, files in os.walk(path):
                [os.chmod(os.path.join(root, f), perm) for f in dirs]
                [os.chmod(os.path.join(root, f), perm) for f in files]
    elif isinstance(path, (list, tuple, ndarray)):
        for f in path:
            f = posixpath(f)
            f.chmod(perm)
            f.parent.chmod(perm)
