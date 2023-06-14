from subprocess import run

from mwr_l12l2.utils.file_uitls import abs_file_path


def run_tropoe(data_path, date, vip_file, apriori_file, tropoe_img='davidturner53/tropoe',
               tmp_path='mwr_l12l2/retrieval/tmp', verbosity=1):
    """Run TROPoe container using podman for one specific retrieval

    Args:
        data_path: path that will be mounted to /data inside the container. Absolute path or relative to project dir
        date: date for which retrieval shall be executed. For now retrievals cannot encompass more than one day.
            Make sure that it is of type :class:`datetime.datetime` or as a string of type 'yyyymmdd' (or 0)
        vip_file: path to vip file relative to :param:`data_path`
        apriori_file:  path to a-priori file relative to :param:`data_path`
        tropoe_img (optional): reference of TROPoe continer image to use. Will take latest available by default
        tmp_path (optional): tmp path that will be mounted to /tmp inside the container. Uses a dummy folder by default
        verbosity (optional): verbosity level of TROPoe. Defaults to 1
    """

    try:
        date_str = date.strftime('%Y%m%d')
    except AttributeError:
        date_str = '{}'.format(date)  # format to handle also integer input

    cmd = ['podman', 'run', '-i', '-u', 'root', '--rm',
           '-e', 'yyyymmdd=' + date_str,
           '-e', 'vfile=/data/' + vip_file,
           '-e', 'pfile=/data/' + apriori_file,
           '-e', 'shour=00',  # achieve time selection over input files, hence consider whole day here
           '-e', 'ehour=24',  # achieve time selection over input files, hence consider whole day here
           '-e', 'verbose={}'.format(verbosity),
           '-v', '{}:/data'.format(abs_file_path(data_path)),
           '-v', '{}:/tmp2'.format(abs_file_path(tmp_path)),
           tropoe_img]
    run(cmd)

if __name__ == '__main__':
    run_tropoe('mwr_l12l2/data', 0, 'tropoe/vip.txt', 'apriori/Xa_Sa.Lindenberg.55level.08.cdf')