Installation
============



from *pypi*
^^^^^^^^^^^
*mwr_l12l2* is directly installable through *pip*. To install the latest released version and its dependencies do

.. code-block::

    pip install mwr_l12l2

for more colorful logging you may want to do

.. code-block::

    pip install mwr_l12l2[colorlog]

from *git*
^^^^^^^^^^
To install *mwr_l12l2* with it's newest developments perform an installation from the source code like follows

1. clone this repository

.. code-block::

    git clone https://github.com/MeteoSwiss/mwr_l12l2.git

2. go into the package directory and install

    - with *pip* (>=21.3)


      .. code-block::

          pip install .

      or

      .. code-block::

          pip install .[colorlog]

    - with *poetry*

      .. code-block::

          poetry install

      or

      .. code-block::

          poetry install -E colorlog