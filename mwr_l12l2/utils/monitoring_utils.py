import os
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
#import matplotlib as mpl
from matplotlib.cm import get_cmap
from matplotlib.backends.backend_pdf import PdfPages
from mwr_l12l2.utils.file_utils import abs_file_path
from mwr_l12l2.utils.config_utils import get_conf
from mwr_l12l2.retrieval.tropoe_helpers import extract_zenith_tbs
from mwr_l12l2.log import logger

np.set_printoptions(precision=2, suppress=True)
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.sans-serif": ["Free sans"],
    "lines.linewidth": 2,
    "figure.figsize": (14, 18),
    "figure.autolayout": True,
    "axes.grid": True,
    "grid.linestyle": "--",
    "grid.alpha": 0.7,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "legend.fontsize": 12,
    })

def save_single_pdf(filename, figures):
    """
    Save all `figures` to a single PDF. Initially taken from Jonas Hagen
    """
    with PdfPages(filename) as pdf:
        for fig in figures:
            pdf.savefig(fig)
            
def read_mwr_summary_csv(file_path="mwr_raw2l1_summary.csv"):
    """
    Read MWR raw2l1 summary CSV file.
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        pandas.DataFrame: DataFrame containing the CSV data
    """
    try:
        # Using pandas for easy data manipulation
        df = pd.read_csv(file_path)
        logger.info(f"Successfully read {len(df)} rows from {file_path}")
        return df
    except FileNotFoundError:
        logger.error(f"CSV file not found: {file_path}")
        raise FileNotFoundError(f"Summary CSV file not found: {file_path}")
    except Exception as e:
        logger.error(f"Error reading CSV file {file_path}: {str(e)}")
        raise

def set_full_day_xlim(ax, reference_time):
    """
    Set x-axis limits to span a full day (00:00 to 23:59) based on a reference time.
    
    Args:
        ax: matplotlib axis object
        reference_time: pandas timestamp or datetime-like object to determine the day
    """
    if reference_time is None:
        return
    
    # Convert to pandas timestamp if needed
    ref_time = pd.to_datetime(reference_time)
    
    # Get the start and end of the day
    day_start = ref_time.normalize()  # 00:00:00
    day_end = day_start + timedelta(days=1) - timedelta(minutes=1)  # 23:59:00
    
    ax.set_xlim(day_start, day_end)
    
    # Format x-axis to show hours
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_minor_locator(mdates.HourLocator())

class ObservationMinusBackground(object):
    """Class to handle observation data minus background data"""

    def __init__(self, wigos, inst_id, tropoe_OmB_file, tropoe_output_config):
        self.wigos = wigos
        self.inst_id = inst_id
        self.tropoe_OmB_file = tropoe_OmB_file
        if isinstance(tropoe_output_config, dict):
            self.conf = tropoe_output_config
        elif os.path.isfile(tropoe_output_config):
            self.conf = get_conf(tropoe_output_config)
        else:
            raise FileExistsError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
        
        # ID of the zenith tb in tropoe OmB file:
        self.brightness_temperature_zenith = self.conf['zenithTb']
        
    def read_tropoe(self):
        """Read the tropoe OmB file and extract relevant data"""
        ds = xr.open_dataset(self.tropoe_OmB_file)
        ds = extract_zenith_tbs(ds, self.conf)
        self.ds_omb = ds
    
    def plot_omb(self, output_dir):
        # Plot the OmB time series for all frequencies in jpg
        
        ds = self.ds_omb
        frequency = ds.frequency
        # Create figure with time series on top, stats on bottom
        fig = plt.figure(figsize=(16, 10))
        
        # Top subplot spanning full width: OmB time series
        ax_top = plt.subplot2grid((2, 2), (0, 0), colspan=2)
        
        cmap = get_cmap('viridis', len(frequency))
        legend_elements_kband = []
        
        for i, f in enumerate(frequency):
            col = cmap(i)
            diff_tb_f = ds.Tb.sel(frequency=f) - ds.Tb_simulated.sel(frequency=f)
            diff_tb_f.plot(ax=ax_top, x='time', color=col, label=str(f.data)+' GHz')
            legend_elements_kband.append(plt.Line2D([0], [0], color=col, label=str(f.data)+' GHz'))

        ax_top.set_xlabel('')
        ax_top.set_ylabel(r'$\Delta$ Tb (K)')
        ax_top.set_ylim(-10,10)
        ax_top.legend(handles=legend_elements_kband, loc='best', fontsize=8, ncol=2)
        ax_top.set_title('O-B for '+self.wigos+'_'+self.inst_id)

        # Bottom left subplot: K-band statistics
        ax_kband = plt.subplot2grid((2, 2), (1, 0))
        
        ds_stats = ds.Tb - ds.Tb_simulated
        k_band_data = ds_stats.where(frequency<32, drop=True)
        k_band_positions = k_band_data.frequency.values
        k_band_values = [k_band_data.sel(frequency=freq).values for freq in k_band_positions]
        ax_kband.boxplot(k_band_values, positions=k_band_positions, widths=0.5, 
                         patch_artist=True, boxprops=dict(facecolor='blue', alpha=0.5))
        ax_kband.set_xlabel('Frequency')
        ax_kband.set_ylabel(r'$\Delta$ Tb (K)')
        ax_kband.set_ylim(-10,10)
        ax_kband.set_title('K-band OmB statistics')
        
        # Bottom right subplot: V-band statistics
        ax_vband = plt.subplot2grid((2, 2), (1, 1))
        
        v_band_data = ds_stats.where(frequency>=32, drop=True)
        v_band_positions = v_band_data.frequency.values
        v_band_values = [v_band_data.sel(frequency=freq).values for freq in v_band_positions]
        ax_vband.boxplot(v_band_values, positions=v_band_positions, widths=0.5,
                         patch_artist=True, boxprops=dict(facecolor='orange', alpha=0.5))
        ax_vband.set_xlabel('Frequency')
        ax_vband.set_ylabel(r'$\Delta$ Tb (K)')
        ax_vband.set_ylim(-10,10)
        ax_vband.set_title('V-band OmB statistics')

        plt.tight_layout()
        filename =  os.path.join(output_dir, f"L1_{self.wigos}_{self.inst_id}_{self.ds_omb.time[0].dt.strftime('%Y%m%d').item()}_OmB.jpg")
        fig.savefig(filename)
        print('Saved OmB plot to {}'.format(filename))

class Level1(object):
    # Collection of function to deal with MWR L1 E-Profile data
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def plot_tb_zenith(self, ds):
        # Plot the brightness temperature at zenith:
        # select observation at zenith:
        tb = ds.tb.where(ds.ele>88.0, drop=True)

        fig, axs = plt.subplots(3, 1, figsize=(16, 12))
        
        # Define one color per frequency bands derived from 'viridis' colormap
        cmap = get_cmap('viridis', len(ds.frequency))
        legend_elements_kband = []
        legend_elements_vband = []
        # liquid_cloud_flag = ds.liquid_cloud_flag
        for i, f in enumerate(ds.frequency):
            col = cmap(i)
            # Flags are defined for each frequency, 0 is good data, more than 0 is flagged data
            flags = ds.quality_flag
             
            tb_f = tb.sel(frequency=f)
            
            if f < 35:
                # plot good data with a dot marker
                tb_f.where(flags.sel(frequency=f)==0).plot(ax=axs[0], x='time', color=col, label=str(f.data)+' GHz') 
                
                #tb_f.where(flags.sel(frequency=f)>0).plot(ax=axs[0], x='time', color=col, linewidth=6, label=str(f.data)+' GHz')
                legend_elements_kband.append(plt.Line2D([0], [0], color=col, label=str(f.data)+' GHz'))

                # in the third plot, plot the difference between 31.8 Ghz band and each of the other k-band channels
                tb_31 = tb.sel(frequency=31.8, method='nearest')
                tb_diff = tb_31 - tb_f
                tb_diff.plot(ax=axs[2], x='time', label='31.8 - '+str(f.data)+' GHz', color=col, linestyle='none', marker='o', markersize=4)

                # in the 4th and 5th plot, plot the standard deviation of all frequencies coomputed on 10 minutes
                # std_tb_i = tb_f.rolling(time=10, center=True).std().resample(time='10min').mean()
                # std_tb_i.plot(ax=axs[3], x='time', color=col, label=str(f.data)+' GHz')
            else:
                tb_f.where(flags.sel(frequency=f)==0).plot(ax=axs[1], x='time', color=col,label=str(f.data)+' GHz')
                #tb_f.where(flags.sel(frequency=f)>0).plot(ax=axs[1], x='time', color=col, linewidth=6, label=str(f.data)+' GHz')
                legend_elements_vband.append(plt.Line2D([0], [0],  color=col, label=str(f.data)+' GHz'))

                # std_tb_i = tb_f.rolling(time=10, center=True).std().resample(time='10min').mean()
                # std_tb_i.plot(ax=axs[4], x='time', color=col, label=str(f.data)+' GHz')

        # liquid_cloud_flag = ds.liquid_cloud_flag #.where(ds.ele>89.0, drop=True)
        # liquid_cloud_flag.plot(ax=axs[5], x='time', label='Liquid Cloud Flag')

        # Get reference time for setting x-axis limits
        reference_time = ds.time[0].values if len(ds.time) > 0 else None
        
        for ax in axs:
            ax.set_xlabel('')
            ax.set_ylabel('Tb (K)')
            set_full_day_xlim(ax, reference_time)
            

        axs[0].legend(handles=legend_elements_kband, loc='best', fontsize=8, ncol=2)
        axs[1].legend(handles=legend_elements_vband, loc='best', fontsize=8, ncol=2)
        axs[0].set_title('Tb: K-band')
        axs[1].set_title('Tb: V-band')
        axs[2].set_title(r'$\Delta Tb$ to 31.8 GHz')
        
        
        # Add vertical gray band for flagged data (sum>0)
        # only on the first two plots
        sum_flags = ds.quality_flag.sum(dim='frequency')
        axs[0].fill_between(ds.time, 0, 1, where=(sum_flags>0), color='gray', alpha=0.3, transform=axs[0].get_xaxis_transform())
        axs[1].fill_between(ds.time, 0, 1, where=(sum_flags>0), color='gray', alpha=0.3, transform=axs[1].get_xaxis_transform())

               
        #fig.suptitle('Brightness Temperature at Zenith')

        return fig
    
    def plot_tb_spectra(self, ds, timeperiod=None):
        if timeperiod is None:
            tb = ds.tb.where(ds.ele>88.0, drop=True)
        else:
            # Select the time period
            tb = ds.tb.where(ds.ele>88.0, drop=True).sel(time=timeperiod)
            
        # compute and plot the averaged spectra during this time:
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # Instead of plotting the mean spectra, we will plot hourly averaged spectra to see the variability during the day
        
        tb_hourly = tb.resample(time='1H').mean()
        
        for t in tb_hourly.time:
            tb_hourly.sel(time=t).plot(ax=ax, marker='o', label=pd.to_datetime(t.data).strftime('%H:%M'))
                  
        ax.set_xlabel('Frequency (GHz)')
        ax.set_ylabel('Tb (K)')
        ax.set_title('Hourly averaged spectra at zenith')
        ax.legend()

        return fig

    def plot_scan(self, ds):
        tb = ds.tb.where(ds.ele<88.0, drop=True)

        # Plot the scan of the MWR L1 E-Profile data
        fig, ax = plt.subplots(1, 1, figsize=(8, 12))

        for f in ds.frequency:
            tb.sel(frequency=f).plot(ax=ax, x='time', label=str(f.data)+' GHz')
        
        # Set full day x-axis limits
        reference_time = ds.time[0].values if len(ds.time) > 0 else None
        set_full_day_xlim(ax, reference_time)
        
        ax.set_title('Scan of the MWR L1')
        ax.set_xlabel('')
        ax.set_ylabel('Tb (K)')
        ax.legend()

        return fig

    def plot_housekeeping(self, ds):
        # Plot the housekeeping data
       
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        for rec in ds.receiver_nb:
            #ds.t_amb.sel(receiver_nb=rec).plot(ax=ax, x='time', label='Tamb, rec '+str(rec.data))
            ds.t_rec.sel(receiver_nb=rec).plot(ax=ax, x='time', label='Trec, rec '+str(rec.data))
            ds.tn.sel(receiver_nb=rec).plot(ax=ax, x='time', label='TN, rec '+str(rec.data))

        # Set full day x-axis limits
        reference_time = ds.time[0].values if len(ds.time) > 0 else None
        set_full_day_xlim(ax, reference_time)
        #ax.set_ylim(250, 320)
        ax.set_title('Housekeeping Data')
        ax.set_xlabel('')
        ax.set_ylabel('T (K)')
        ax.legend()

        return fig
    
    def plot_meteo(self, ds):
        # Plot the meteorological data measured by the MWR
        # Variables to plots are air_pressure, air_temperature, relative_humidity, wind_speed, wind_direction, rain_rate
        
        fig, axs = plt.subplots(3, 1, figsize=(16, 12))
        reference_time = ds.time[0].values if len(ds.time) > 0 else None
        
        # Plots air temperature and relative humidity on the same plots with secondary y-axis
        axs[0].plot(ds.time, ds.air_temperature, label='Air Temperature', color='tab:orange')
        axs2 = axs[0].twinx()
        axs2.plot(ds.time, ds.relative_humidity, label='Relative Humidity', color='tab:blue')
        axs[0].set_title('Air Temperature and Relative Humidity')
        axs[0].set_ylabel('Air Temperature (K)', color='tab:orange')
        axs2.set_ylabel('Relative Humidity (%)', color='tab:blue')
        axs[0].tick_params(axis='y', labelcolor='tab:orange')
        axs2.tick_params(axis='y', labelcolor='tab:blue')
        
        # Same with Pressure and Wind Speed
        axs[1].plot(ds.time, ds.wind_speed, label='Wind Speed', color='tab:orange')
        
        axs3 = axs[1].twinx()
        axs3.plot(ds.time, ds.air_pressure, label='Air Pressure', color='tab:blue')
        
        axs[1].set_title('Air Pressure and Wind Speed')
        axs[1].set_ylabel('Wind Speed (m/s)', color='tab:orange')
        axs3.set_ylabel('Air Pressure (hPa)', color='tab:blue')
        axs3.tick_params(axis='y', labelcolor='tab:blue')
        axs[1].tick_params(axis='y', labelcolor='tab:orange')
        
        # Finally Rain Rate
        axs[2].plot(ds.time, ds.rain_rate, label='Rain Rate', color='tab:blue')
        axs[2].set_title('Rain Rate')
        axs[2].set_ylabel('Rain Rate (mm/h)', color='tab:blue')
        axs[2].tick_params(axis='y', labelcolor='tab:blue')
        
        for ax in axs:
            ax.set_xlabel('')
            set_full_day_xlim(ax, reference_time)
        return fig

    def find_lwcl_free(self, ds, path_to_lidar=None, output_plot=None):
        """
        This is a copy of the MWRpy function to find liquid water cloud free periods using 31.4 GHz TB variability.
        Uses water vapor channel as proxy for a humidity dependent threshold.

        Refactored to work directly with xarray ds instead of dict

        Args:
            ds (_type_): _description_
            path_to_lidar (_type_): _description_
        """
        # Different frequencies for window and water vapor channels depending on instrument type
        freq_win = np.where(
            (np.isclose(ds["frequency"].values, 31.4, atol=2))
            | (np.isclose(ds["frequency"].values, 190.8, atol=1))
        )[0]
        freq_win = np.array([freq_win[0]]) if len(freq_win) > 1 else freq_win
        freq_wv = np.where(
            (np.isclose(np.round(ds["frequency"][:], 1), 22.2))
            | (np.isclose(np.round(ds["frequency"][:], 1), 183.9))
        )[0]

        # Improve the above by using xarray existing methods
        #tb = ds["tb"].sel(frequency=31.4, method="nearest", tolerance=1, drop=True)

        if len(freq_win) == 1 and len(freq_wv) == 1:
            #tb = np.squeeze(ds["tb"][:, freq_win])
            tb = ds["tb"].isel(frequency=freq_win)
            # tb[(ds["pointing_flag"][:] == 1) | (ds["ele"][:] < 89.0)] = (
            #     np.nan
            # )
            tb = tb.squeeze(dim='frequency', drop=True)
            #ind = utils.time_to_datetime_index(ds["time"][:])
            #tb_df = pd.DataFrame({"Tb": tb}, index=ind)
            tb_zenith = tb.where(ds["pointing_flag"] == 0, drop=True).where((ds["ele"] > 89.0) & (ds["ele"] < 91.0), drop=True)
            mean_diff_t = np.nanmean(tb.time.diff(dim='time').dt.seconds)
            time_span = (tb.time[-1] - tb.time[0]).dt.total_seconds()/60

            print(f"Mean time difference: {mean_diff_t} seconds, Time span: {time_span} minutes")

            # Definition of the different resampling time based on time_span and mean_diff_t
            if mean_diff_t < 1.8:
                n_sampled_std = 60 # "1min"
                n_sampled_final = 180 # "3min"
            else:
                n_sampled_std = 90 # "3min"
                n_sampled_final = 600 # "10min"
               
            # resampling_time_std = "3min" if mean_diff_t < 1.8 else "10min"
            # resampling_time_ratio = "20min" if mean_diff_t < 1.8 else "60min"
            tb_std = tb_zenith.rolling(time=n_sampled_std, center=True).std()
            tb_mx = tb_std.rolling(time=n_sampled_final, center=True).max()
            
            # In order to compute the ratio, we need to get rid of the frequency coordinates
            tb_wv = ds["tb"].isel(frequency=freq_wv)
            tb_wv = tb_wv.squeeze(dim='frequency', drop=True)

            tb_rat = tb_wv / tb

            tb_rat = tb_rat.rolling(time=n_sampled_final, center=True).max()

            threshold_rat = tb_rat * 0.075
            ds['liquid_cloud_flag'] = xr.where(
                tb_mx < threshold_rat,
                0,
                1,
            )
        # set to nan where tb_mx is nan TODO: still does not work...
        ds['liquid_cloud_flag'] = xr.where(threshold_rat.isnull(), 2, ds['liquid_cloud_flag'])
        # Set the scan flag to 2
        ds['liquid_cloud_flag'] = xr.where((ds["ele"] > 89.0) & (ds["ele"] < 91.0), ds['liquid_cloud_flag'], 2)
        # also fill nans with 2
        ds['liquid_cloud_flag'] = ds['liquid_cloud_flag'].fillna(2)

        if output_plot:
            # Plot different quantities and the resulting liquid cloud flag
            fig, axs = plt.subplots(3, 1, figsize=(18, 16))
            rain_flag = ds.quality_flag.isel(frequency=1).cf == 'rain_detected'

            rain_flag.where(rain_flag, drop=False).plot(ax=axs[2], x='time', linewidth=0, marker='s', label='Rain Flag')

            tb_zenith.plot(ax=axs[0], x='time', label='Zenith Tb at ' + str(ds.frequency[freq_win].values[0]) + ' GHz')
            tb_mx.plot(ax=axs[1], x='time', label='max(std(Tb))')
            tb_rat.plot(ax=axs[1], x='time', label='Tb Ratio ' + str(ds.frequency[freq_win].values[0]) + ' / ' + str(ds.frequency[freq_wv].values[0]))
            threshold_rat.plot(ax=axs[1], x='time', label='Threshold Ratio')
            ds['liquid_cloud_flag'].where((ds["ele"] > 89.0) & (ds["ele"] < 91.0), drop=False).plot(ax=axs[2], x='time', linewidth=0, marker='x', label='LCFz: 1=cloud')
            ds['liquid_cloud_flag'].where((ds["ele"] < 89.0) | (ds["ele"] > 91.0), drop=False).plot(ax=axs[2], x='time', linewidth=0, marker='.', label='LCFscan')
            # For additional information, add quality flag (quality_flag>0)

            axs[1].set_ylim(0,2.5)
            
            # Set full day x-axis limits for all axes
            reference_time = ds.time[0].values if len(ds.time) > 0 else None
            
            for ax in axs:
                ax.legend()
                ax.set_xlabel('Time')
                ax.set_ylabel('[K]')
                set_full_day_xlim(ax, reference_time)

            axs[2].set_ylabel('Liquid Cloud Flag')

            # filename
            datetime_str = np.datetime_as_string(ds.time[0], unit='m')
            filename = f"lwcl_free_{self.wigos}_{self.instr_id}_{datetime_str}.png"
            plt.savefig(os.path.join(output_plot, filename))
            plt.close(fig)

        return ds


    def plot_l1(self, ds, date_start=None, date_stop=None, plot_tb=True, plot_scan=True, plot_housekeeping=True, plot_meteo=True, plot_tb_spectra=True):
        """Plot MWR L1 E-Profile data"""
        # Create the output directory
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Generate base filename
        if date_start is None:
            datetime_str = datetime_str = pd.to_datetime(ds.time[0].values).strftime('%Y%m%d')
        else:
            datetime_str = date_start.strftime('%Y%m%d')
        
        base_filename = f"L1_{ds.wigos_station_id}_{ds.instrument_id}_{datetime_str}"

        # Plot and save each figure individually
        if plot_tb:
            fig = self.plot_tb_zenith(ds)
            filename = os.path.join(self.output_dir, f"{base_filename}_zenith.jpg")
            fig.suptitle(ds.attrs['title'], fontsize=18)
            fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
            plt.close(fig)

        if plot_scan:
            fig = self.plot_scan(ds)
            filename = os.path.join(self.output_dir, f"{base_filename}_scan.jpg")
            fig.suptitle(ds.attrs['title'], fontsize=18)
            fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
            plt.close(fig)

        if plot_housekeeping:
            fig = self.plot_housekeeping(ds)
            filename = os.path.join(self.output_dir, f"{base_filename}_housekeeping.jpg")
            fig.suptitle(ds.attrs['title'], fontsize=18)
            fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
            plt.close(fig)

        if plot_meteo:
            fig = self.plot_meteo(ds)
            filename = os.path.join(self.output_dir, f"{base_filename}_meteo.jpg")
            fig.suptitle(ds.attrs['title'], fontsize=18)
            fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
            plt.close(fig)

        if plot_tb_spectra:
            fig = self.plot_tb_spectra(ds, timeperiod=slice(date_start, date_stop))
            filename = os.path.join(self.output_dir, f"{base_filename}_spectra.jpg")
            fig.suptitle(ds.attrs['title'], fontsize=18)
            fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
            plt.close(fig)
            
if __name__ == "__main__":
    omb_test_file = "/home/eric/retrieval/level2/tropoe_out_0-250-1001-07151A.20251016.100030.nc"
    tropoe_conf_file = abs_file_path('mwr_l12l2/config/tropoe_output_config.yaml')
    omb = ObservationMinusBackground(wigos='0-250-1001-07151', inst_id='A', tropoe_OmB_file=omb_test_file, tropoe_output_config=tropoe_conf_file)
    omb.read_tropoe()
    omb.plot_omb(output_dir='/home/eric/monitoring/quicklooks/')
