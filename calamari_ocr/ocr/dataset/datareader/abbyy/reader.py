import os
import numpy as np
from typing import List, Generator
from PIL import Image
from tfaip.base.data.pipeline.definitions import PipelineMode, TARGETS_PROCESSOR, INPUT_PROCESSOR

from calamari_ocr.ocr.dataset.params import InputSample, SampleMeta
from calamari_ocr.ocr.dataset.datareader.abbyy.xml import XMLReader, XMLWriter
from tqdm import tqdm

from calamari_ocr.ocr.dataset.datareader.base import DataReader
from calamari_ocr.utils import split_all_ext
from calamari_ocr.utils.image import load_image


class AbbyyReader(DataReader):
    def __init__(self,
                 mode: PipelineMode,
                 files: List[str] = None,
                 xmlfiles: List[str] = None,
                 skip_invalid=False,
                 remove_invalid=True,
                 binary=False,
                 non_existing_as_empty=False,
                 ):

        """ Create a dataset from a Path as String

        Parameters
         ----------
        files : [], required
            image files
        skip_invalid : bool, optional
            skip invalid files
        remove_invalid : bool, optional
            remove invalid files
        """

        super().__init__(
            mode,
            skip_invalid, remove_invalid)

        self.xmlfiles = xmlfiles if xmlfiles else []
        self.files = files if files else []

        self._non_existing_as_empty = non_existing_as_empty
        if len(self.xmlfiles) == 0:
            from calamari_ocr.ocr.dataset import DataSetType
            self.xmlfiles = [split_all_ext(p)[0] + DataSetType.gt_extension(DataSetType.ABBYY) for p in files]

        if len(self.files) == 0:
            self.files = [None] * len(self.xmlfiles)

        self.book = XMLReader(self.files, self.xmlfiles, skip_invalid, remove_invalid).read()
        self.binary = binary

        for p, page in enumerate(self.book.pages):
            for l, line in enumerate(page.getLines()):
                for f, fo in enumerate(line.formats):
                    self.add_sample({
                        "image_path": page.imgFile,
                        "xml_path": page.xmlFile,
                        "id": "{}_{}_{}_{}".format(os.path.splitext(page.xmlFile if page.xmlFile else page.imgFile)[0], p, l, f),
                        "line": line,
                        "format": fo,
                    })

    def store_text(self, sentence, sample, output_dir, extension):
        # an Abbyy dataset stores the prediction in one XML file
        sample["format"].text = sentence

    def store(self, extension):
        for page in tqdm(self.book.pages, desc="Writing Abbyy files", total=len(self.book.pages)):
            XMLWriter.write(page, split_all_ext(page.xmlFile)[0] + extension)

    def _sample_iterator(self):
        return zip(self.files, self.xmlfiles)

    def _generate_epoch(self, text_only) -> Generator[InputSample, None, None]:
        fold_id = -1
        for p, page in enumerate(self.book.pages):
            if self.mode in INPUT_PROCESSOR:
                img = load_image(page.imgFile)
                if self.binary:
                    img = img > 0.9
            else:
                img = None

            for l, line in enumerate(page.getLines()):
                for f, fo in enumerate(line.formats):
                    fold_id += 1
                    sample_id = "{}_{}_{}_{}".format(os.path.splitext(page.xmlFile if page.xmlFile else page.imgFile)[0], p, l, f)
                    text = None
                    if self.mode in TARGETS_PROCESSOR:
                        text = fo.text

                    if text_only:
                        yield InputSample(None, text, SampleMeta(id=sample_id, fold_id=fold_id))

                    else:
                        cut_img = None
                        if self.mode in INPUT_PROCESSOR:
                            ly, lx = img.shape

                            # Cut the Image
                            cut_img = img[line.rect.top: -ly + line.rect.bottom, line.rect.left: -lx + line.rect.right]

                            # add padding as required from normal files
                            cut_img = np.pad(cut_img, ((3, 3), (0, 0)), mode='constant', constant_values=cut_img.max())

                        yield InputSample(cut_img, text, SampleMeta(id=sample_id, fold_id=fold_id))

    def _load_sample(self, sample, text_only) -> Generator[InputSample, None, None]:
        raise NotImplementedError
