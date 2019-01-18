Building manylinux1 wheels

1. Clone ptvsd to base dir (say `C:\git`), so ptvsd source must be at `C:\git\ptvsd`.
2. Create dir `dist` under `C:\git\dist`.
3. Run following command:
* x86_64: `docker run --rm -v C:\git:/io -w /io quay.io/pypa/manylinux1_x86_64:latest /io/ptvsd/linux/build_plat.sh /io/ptvsd /io/dist cp37-cp37m`
* i686: `docker run --rm -v C:\git:/io -w /io quay.io/pypa/manylinux1_i686:latest /io/ptvsd/linux/build_plat.sh /io/ptvsd /io/dist cp37-cp37m`
4. After the run the built wheel should be in `C:\git\dist`. 

Other python ABI options:
* cp27-cp27m
* cp27-cp27mu
* cp34-cp34m
* cp35-cp35m
* cp36-cp36m
* cp37-cp37m