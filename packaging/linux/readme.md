Building manylinux1 wheels

1. Clone debugpy to a base directory (say `C:\git`), giving debugpy repository at `C:\git\debugpy`.
2. Create dir `dist` under `C:\debugpy\dist`.
3. Run the following command:
* x86_64: `docker run --rm -v C:\git:/io -w /io quay.io/pypa/manylinux1_x86_64:latest /io/debugpy/linux/build_plat.sh /io/debugpy /io/dist cp37-cp37m`
* i686: `docker run --rm -v C:\git:/io -w /io quay.io/pypa/manylinux1_i686:latest /io/debugpy/linux/build_plat.sh /io/debugpy/io/dist cp37-cp37m`
4. After the run the built wheel should be in `C:\git\dist`. 

Other python ABI options:
* cp27-cp27m
* cp27-cp27mu
* cp35-cp35m
* cp36-cp36m
* cp37-cp37m
* cp38-cp38m
