import yaml

class RequestGenerator:

    def __int__(self, request_file, stn_config_files_path):
        self.request_file = request_file
        self.stn_config_files_path = stn_config_files_path
        self.stn_configs = []
        self.file_contents = []  # a list of strings, one for each line

    def run(self):
        self.get_stn_config()
        self.write_core_request()
        self.write_stn_request()
        self.dump_to_file()

    def get_stn_config(self):
        #  TODO self.stn_configs = set of dicts with outfile for ECMWF data, lat and lon for each stn
        pass

    def write_core_request(self):
        """write general request settings for first station"""

    def write_stn_request(self):
        """add station-specific settings to request"""
        for ind, conf in enumerate(self.stn_configs):
            if ind > 0:
                self.file_contents.append('retrieve,')

            # TODO: write area and output file name. for area use round to precision of value for grid

    def dump_to_file(self):
        with open(self.request_file, 'w') as f:
            f.write(',\n'.join(self.file_contents))




