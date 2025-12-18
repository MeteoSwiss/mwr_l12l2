import numpy as np
import pandas as pd
import xarray as xr


# def get_from_nc_files(files_in, concat_dim='time'):
#     """read (several) NetCDF input files to a :class:`xarray.Dataset` and fix time encoding for correct nc output"""
#     data = xr.open_mfdataset(files_in, data_vars='all', concat_dim=concat_dim, combine='nested')
#     data = drop_duplicates(data, dim=concat_dim)

#     # correct time encoding (especially units) which is broken by open_mfdateset by explicitly loading first file
#     data_first = xr.open_dataset(files_in[0])
#     data = set_encoding(data, ['time', 'time_bnds'], data_first.time.encoding)

#     return data

def get_from_nc_files(files_in, concat_dim='time'):
    """Read a list of MWR L1 E-Profile files and return a xarray dataset"""

    # Read the first file to get the time dimension
    # ds = xr.open_dataset(files_in[0], engine='netcdf4')
    # Create a list of datasets
    ds_list = []
    for f in files_in:
        ds_list.append(xr.open_dataset(f, engine='netcdf4'))
    # Concatenate the list of datasets
    data = xr.concat(ds_list, data_vars='all', dim=concat_dim)
    # Identify duplicated time values
    _, index = np.unique(data.time, return_index=True)
    # Keep only the unique time values
    data = data.isel(time=index)
    # Sort the dataset by time
    data = data.sortby(concat_dim)
    return data

def drop_duplicates(ds, dim):
    """drop duplicates from all data in ds for duplicates in dimension vector

    Args:
        ds: :class:`xarray.Dataset` or :class:`xarray.DataArray` containing the data
        dim: string indicating the dimension name to check for duplicates
    Returns:
        ds with unique dimension vector
    """

    _, ind = np.unique(ds[dim], return_index=True)  # keep first index but assume duplicate values identical anyway
    return ds.isel({dim: ind})


def set_encoding(ds, vars, enc):
    """(re-)set encoding of variables in a dataset

    Args:
        ds: :class:`xarray.Dataset` containing the data
        vars: list of variables for which encoding is to be adapted
        enc: encoding dictionary (containing e.g. units) that encoding of the respective variables shall to be set to.
    Returns:
        ds with updated encoding for var in :obj:`vars`
    """
    for var in vars:
        ds[var].encoding = enc
    return ds


def get_nearest(data, find_vals):
    """find values in data nearest values in the input data"""
    x = np.unique(data)
    out = []
    for fv in find_vals:
        out.append(x[np.abs(x-fv).argmin()])
    return out


def has_data(ds, var):
    """check if a variable in a :class:`xarray.Dataset` exists and contains non-NaN data"""
    if var in ds and not ds[var].isnull().all():
        return True
    else:
        return False


def datetime64_to_str(x, date_format):
    """transform :class:`numpy.datetime64` to a datestring corresponding to 'date_format'

    Args:
        x: datetime as :class:`numpy.datetime64` object
        date_format: date format understood by :class:`datetime.datetime`
    """
    t = pd.to_datetime(x)
    return t.strftime(date_format)


def datetime64_to_hour(x):
    """transform :class:`numpy.datetime64` to a float representing time of day in hours"""
    date_format = '%H:%M:%S.%f'
    hour_frac = np.array([1, 60, 3600])
    dstr = datetime64_to_str(x, date_format)
    hms = np.array(list(map(float, dstr.split(':'))))
    return np.sum(hms / hour_frac)


def scalars_to_time(ds, variables, time_dim='time'):
    """expand scalar variables onto time dimension to form an array of len(time) containing identical values

    Args:
        ds: :class:`xarray.Dataset` containing all requested scalar variables and the time dimension to transform to
        variables: list of variables to expand onto the time dimension. These will be replaced in-place
        time_dim (optional): name of the time dimension. Defaults to 'time'.
    """
    for var in variables:
        ds.update({var: (time_dim, ds[var].values * np.ones(ds[time_dim].shape))})
    return ds

def vectors_to_time(ds, variables, time_dim='time'):
    """expand constant vector variables onto time dimension to form an array of len(time) containing identical values
    TODO: merge with scalars_to_time

    Args:
        ds: :class:`xarray.Dataset` containing all requested scalar variables and the time dimension to transform to
        variables: list of variables to expand onto the time dimension. These will be replaced in-place
        time_dim (optional): name of the time dimension. Defaults to 'time'.
    """
    for var in variables:
        ds[var] = ds[var].expand_dims(time=ds[time_dim])
    return ds

def lists_to_np(indict):
    """transform all values of a dict with type list to a :class:`numpy.ndarray`"""
    for key, val in indict.items():
        if isinstance(val, list):
            indict[key] = np.array(val)
    return indict

class InstrumentSelector(object):
    """Class that select and the instrument and list the files needed for the retrieval
    It is now done outside of the retrieval class to prepare for parallel retrievals.

    Essentially just running the original method "select_instrument" and "list_obs_files" from the retrieval class.

    Args:
        conf: configuration file or dictionary
    """

    def __init__(self, conf):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            logger.error("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        # set by select_instrument():
        self.wigos = None
        self.inst_id = None
        self.inst_conf = None

        # set by list_obs():
        self.mwr_files = None
        self.alc_files = None

    def select_oldest(self):
        """select instrument which has oldest (processable) mwr file in input dir"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work.
        #       but better use ecflow to not data listing for other nodes until end of prepare_eprofile_main
        # find oldest file in the folder and get station id from filename (or from file content)
        # list files in input dir
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                               '{}*.nc'.format(self.conf['data']['mwr_file_prefix'])))
        
        if not list_of_files:
            logger.error('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
        
        # extract filename and dates of all files
        list_of_file_date = [os.path.basename(x).split('/')[-1].split('_')[3] for x in list_of_files]
        list_of_dates = [dt.datetime.strptime(x[1:-3], '%Y%m%d%H%M%S') for x in list_of_file_date]

        # get oldest file based on the date in the filename:
        id_oldest = list_of_dates.index(min(list_of_dates))
        oldest_file = list_of_files[id_oldest]
        
        # get station id from filename
        self.wigos = oldest_file.split('/')[-1].split('_')[2]
        #self.wigos = '0-20008-0-INO'
        
        self.inst_id = oldest_file.split('/')[-1].split('_')[3][0]
        #self.inst_id = 'A'

        inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                               self.wigos, self.inst_id)
        self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))

    def set_instrument(self, wigos, inst_id):
        """set instrument and config file manually providing wigos and inst_id"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work.
        #       but better use ecflow to not data listing for other nodes until end of prepare_eprofile_main

        logger.info('Setting instrument to {} {}'.format(wigos, inst_id))

        # set wigos and station id
        self.wigos = wigos
        self.inst_id = inst_id

        # List files to check it some exist
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        
        if not list_of_files:
            err_msg = 'No MWR data found in {}'.format(self.conf['data']['mwr_dir'])
            logger.error(err_msg)
            raise MissingDataError(err_msg)

        inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                               self.wigos, self.inst_id)
        self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))

    def list_obs_files(self):
        """get file lists for the selected station

        Note:
             this method shall list all (MWR) files not just the ones matching time settings. Like that old (obsolete)
             files are removed when :meth:`prepare_obs` is run with delete_mwr_in=True
        """
        self.mwr_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        self.alc_files = glob.glob(os.path.join(self.conf['data']['alc_dir'],
                                                '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'], self.wigos)))
        if not self.mwr_files:
            err_msg = ('No MWR data for {} {} found in {}. These files must have been removed between station selection'
                       ' and file listing. This should not happen!'.format(self.wigos, self.inst_id,
                                                                           self.conf['data']['mwr_dir']))
            logger.critical(err_msg)
            raise MissingDataError(err_msg)

