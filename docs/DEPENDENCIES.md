# 依赖

运行时没有第三方托管服务。程序只直连 `*.weixin.qq.com` 和 `api2.cursor.sh`。

安装不访问 PyPI。box 压缩包自带下面这些 wheel，`install.sh` 先核对 SHA256，再用 `pip --no-index` 装进本地 `venv`。

平台：Linux x86_64 与 aarch64，CPython 3.11、3.12、3.13。Pillow 这些 wheel 需要 glibc >= 2.27。

| 包 | 版本 | 作用 |
|---|---|---|
| cryptography | 50.0.2 | 本机 AES-128-ECB，解密微信 CDN 媒体 |
| cffi | 2.1.1 | cryptography 的本机依赖 |
| pycparser | 3.12 | cffi 的本机依赖 |
| pillow | 13.0.0 | 本机把二维码画成 PNG，不把内容送到二维码网站 |
| qrcode | 8.2 | 本机生成二维码 |

SHA256 与发布这些 wheel 的官方包索引摘要一致。压缩包里的 `SHA256SUMS` 是安装时实际核对的清单，内容与下表相同。

```
3311ed60d36f83378794e1009ac6258bafbf81f7888b4caa7b35a521e3f95813  cffi-2.1.1-cp311-cp311-manylinux2014_aarch64.manylinux_2_17_aarch64.whl
34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632  cffi-2.1.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
68e62fe11f30d5ca8289242866f0a5291402d8529ca2178ab8afc5c9694ae890  cffi-2.1.1-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.whl
c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf  cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
f16c709686a78c727bbbf059f92b0bf41c6fc60deec706d2dc19f529175a6125  cffi-2.1.1-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl
a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2  cffi-2.1.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
79def8d059362e7831389ed3be0ecdf58a89386e1271e35dd9f5af84e81bffd0  cryptography-50.0.2-cp311-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl
630ebfea3bf689d075f82316324ff7433dc447fe6bc1bfc76524b74b4a9567d2  cryptography-50.0.2-cp311-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
7c88c10dd432f3b39ccdafc9ed81d0c21b8fd634502574da76d1bfa4fe2c76d0  pillow-13.0.0-cp311-cp311-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
a625df9a2a5597fa5e5266e01aefc82604bb85d291e3547981e863560d75da6c  pillow-13.0.0-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
8bf295fe459343bc6093c8e5e0df60bfa189e0fcb775a22e2c2488fdeccc6c0d  pillow-13.0.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
42d63be3af4f9b951b199b0a9d23365d37ab14687e6d77b74940432c8515c4ca  pillow-13.0.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
19b66ca0a4d25cc0200b381ce824c7ea090db61427315e73cfb05dbf1b35c369  pillow-13.0.0-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
5f56499c1a74d2b862beb0c33b8016f99d095858455df9d21583bbbc1c15b582  pillow-13.0.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e  pycparser-3.12-py3-none-any.whl
16e64e0716c14960108e85d853062c9e8bba5ca8252c0b4d0231b9df4060ff4f  qrcode-8.2-py3-none-any.whl
```
