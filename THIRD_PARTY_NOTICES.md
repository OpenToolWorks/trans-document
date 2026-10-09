# Third-Party Notices

TransDocument uses third-party Python packages and assets. Copyright in each component remains with its respective authors and contributors. The project's AGPL-3.0-only license does not replace the licenses of those components.

This notice records the principal components verified in the Windows Python 3.12 development environment on 2026-10-09. Only BabelDOC and Gradio are pinned directly by TransDocument; transitive versions may change when dependencies are installed again. Dependencies are installed separately by pip and are not bundled into the TransDocument wheel.

## Direct dependencies

| Component | Version | License | Purpose / upstream |
| --- | --- | --- | --- |
| BabelDOC | 0.6.4 | GNU AGPL, version 3 | PDF parsing, formulas, translation orchestration, typesetting and PDF generation. [Source and license](https://github.com/funstory-ai/BabelDOC) |
| Gradio | 5.49.1 | Apache-2.0 | Local browser UI, upload, progress and downloads. [Source and license](https://github.com/gradio-app/gradio) |

BabelDOC's license text is supplied in its installed `babeldoc-*.dist-info/licenses/LICENSE`. Gradio's Apache license is supplied in `gradio-*.dist-info/licenses/LICENSE`. A copy of GNU AGPL version 3 is also provided in the project's `LICENSE`.

TransDocument imports these libraries as installed dependencies.

## Principal runtime dependencies

| Component | Observed version | License / notices | Upstream |
| --- | --- | --- | --- |
| PyMuPDF / MuPDF | PyMuPDF 1.28.2 | AGPL-3.0 or an Artifex commercial license; this project uses the open-source distribution | https://github.com/pymupdf/PyMuPDF; https://mupdf.com/ |
| OpenAI Python SDK | 3.26.1 | Apache-2.0; installed license includes Copyright 2026 OpenAI | https://github.com/openai/openai-python |
| gradio-client | 1.13.3 | Apache-2.0 | https://github.com/gradio-app/gradio |
| HTTPX | 0.28.1 | BSD-3-Clause; Copyright 2019 Encode OSS Ltd | https://github.com/encode/httpx |
| ONNX | 1.23.2 | Apache-2.0; wheel contains an additional `NOTICE` for bundled components | https://github.com/onnx/onnx |
| ONNX Runtime | 1.30.0 | MIT; Copyright Microsoft Corporation; includes `ThirdPartyNotices.txt` | https://github.com/microsoft/onnxruntime |
| NumPy | 2.5.3 | BSD-3-Clause and additional bundled-code licenses: 0BSD, MIT, Zlib, CC0-1.0 | https://github.com/numpy/numpy |
| OpenCV Python (headless) | 5.0.0.93 | Apache-2.0 for the Python distribution; retain the wheel's native-library notices | https://github.com/opencv/opencv-python |
| Levenshtein | 0.27.5 | GPL-2.0-or-later | https://github.com/rapidfuzz/Levenshtein |
| Pydantic | 2.11.10 | MIT | https://github.com/pydantic/pydantic |
| Peewee | 4.5.3 | MIT; Copyright 2010 Charles Leifer | https://github.com/coleifer/peewee |
| freetype-py | 2.5.1 | BSD-3-Clause; Copyright 2011-2014 Nicolas P. Rougier; bundled FreeType has its own terms | https://github.com/rougier/freetype-py |
| uharfbuzz | 0.56.3 | Apache-2.0 for the binding; retain notices for the native HarfBuzz library | https://github.com/harfbuzz/uharfbuzz |
| Hyperscan Python binding | 0.9.1 | MIT; Copyright 2017 David Gidwani; native engine notices are separate | https://github.com/darvid/python-hyperscan |
| certifi | 2026.7.22 | MPL-2.0 | https://github.com/certifi/python-certifi |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT), as declared by the installed distribution | https://github.com/ijl/orjson |

Other transitive packages, including FastAPI, Starlette, Uvicorn, SciPy, scikit-learn, Pillow and cryptography, remain under their upstream licenses. The table is an attribution summary, not an exhaustive inventory of all code in dependency wheels. Native wheels can contain additional libraries whose license files must also be preserved when those wheels or an application environment are redistributed.

### PDFMiner included within BabelDOC

BabelDOC includes a PDFMiner-derived implementation under the MIT license. The installed copy of `babeldoc/pdfminer/LICENSE` states:

```text
Copyright (c) 2004-2016  Yusuke Shinyama <yusuke at shinyama dot jp>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Models and fonts downloaded by BabelDOC

These assets are fetched and cached by BabelDOC at runtime; they are not included in this repository or the TransDocument wheel. Their own license and copyright notices apply independently of the Python package license.

- **DocLayout-YOLO DocStructBench ONNX weights:** the downloaded model's [model card](https://huggingface.co/wybxc/DocLayout-YOLO-DocStructBench-onnx) declares Apache-2.0, as does its [base model card](https://huggingface.co/juliozhao/DocLayout-YOLO-DocStructBench). The separate [DocLayout-YOLO source repository](https://github.com/opendatalab/DocLayout-YOLO) uses GNU AGPL version 3; the source and weights must not be assumed to have identical licenses.
- **Noto Sans / Noto Serif and Source Han fonts:** the [BabelDOC-Assets attribution list](https://github.com/funstory-ai/BabelDOC-Assets) identifies SIL Open Font License 1.1 for these families. Preserve each font's copyright, reserved-name information and license when redistributing font files.
- **Go Noto Universal / Go Noto Kurrent:** BabelDOC-Assets links to the [Go Noto Universal project](https://github.com/satbyy/go-noto-universal) and its Unlicense notice. That build-project notice must not be treated as overriding the notices of constituent font data; retain the actual distributed fonts' applicable notices.
- **Additional language fonts:** BabelDOC-Assets lists separate terms for LXGW fonts, Klee and MaruBuri. Use its attribution list and the specific font distribution's license for any such files included in a release.

## License texts and distribution

- GNU AGPL version 3: [`LICENSE`](LICENSE), https://www.gnu.org/licenses/agpl-3.0.html
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- GNU GPL version 2: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
- SIL Open Font License 1.1: https://openfontlicense.org/open-font-license-official-text/

Python dependency distributions retain their full license texts in their `.dist-info` directories and, for some native packages, within the package directory. In particular, keep ONNX's `licenses/NOTICE`, ONNX Runtime's `ThirdPartyNotices.txt`, BabelDOC's PDFMiner license and the additional licenses in numerical/font-processing wheels when distributing those components. This summary does not substitute for those original texts and notices.

Hosted translation APIs such as Gemini and OpenAI are external services, not software distributed by TransDocument. Their service terms govern API use; their names are used only to describe compatible integrations.
