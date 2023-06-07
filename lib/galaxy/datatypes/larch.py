from typing import TYPE_CHECKING

from galaxy.datatypes.data import (
    get_file_peek,
    Text,
)
from galaxy.datatypes.metadata import MetadataElement
from galaxy.datatypes.sniff import (
    build_sniff_from_prefix,
    FilePrefix,
    get_headers,
)

if TYPE_CHECKING:
    from galaxy.model import DatasetInstance


@build_sniff_from_prefix
class AthenaProject(Text):
    """
    Athena project format
    """

    file_ext = "prj"
    compressed = True
    compressed_format = "gzip"

    MetadataElement(
        name="atsym",
        desc="Atom symbol",
        readonly=True,
        visible=True,
    )
    MetadataElement(
        name="bkg_e0",
        desc="Edge energy (eV)",
        readonly=True,
        visible=True,
    )
    MetadataElement(
        name="edge",
        desc="Edge",
        readonly=True,
        visible=True,
    )
    MetadataElement(
        name="npts",
        desc="Number of points",
        readonly=True,
        visible=True,
    )
    MetadataElement(
        name="xmax",
        desc="Maximum energy (eV)",
        readonly=True,
        visible=True,
    )
    MetadataElement(
        name="xmin",
        desc="Minimum energy (eV)",
        readonly=True,
        visible=True,
    )

    def sniff_prefix(self, file_prefix: FilePrefix) -> bool:
        """
        Try to guess if the file is an Athena project file.

        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('test.prj')
        >>> AthenaProject().sniff(fname)
        True
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('Si.cif')
        >>> FEFFInput().sniff(fname)
        False
        """

        return file_prefix.startswith("# Athena project file")

    def set_meta(self, dataset: "DatasetInstance", overwrite: bool = True, **kwd) -> None:
        """
        Extract metadata from @args
        """
        headers = get_headers(dataset.file_name, sep=" = ", count=3, comment_designator="#")
        for header in headers:
            if header[0] == "@args":
                args = header[1][1:-2].split(",")
                break

        index = args.index("'atsym'")
        dataset.metadata.atsym = args[index + 1][1:-1]
        index = args.index("'bkg_e0'")
        dataset.metadata.bkg_e0 = args[index + 1][1:-1]
        index = args.index("'edge'")
        dataset.metadata.edge = args[index + 1][1:-1]
        index = args.index("'npts'")
        dataset.metadata.npts = args[index + 1][1:-1]
        index = args.index("'xmax'")
        dataset.metadata.xmax = args[index + 1][1:-1]
        index = args.index("'xmin'")
        dataset.metadata.xmin = args[index + 1][1:-1]

    def set_peek(self, dataset: "DatasetInstance", **kwd) -> None:
        if not dataset.dataset.purged:
            dataset.peek = get_file_peek(dataset.file_name)
            dataset.info = (
                f"atsym: {dataset.metadata.atsym}\n"
                f"bkg_e0: {dataset.metadata.bkg_e0}\n"
                f"edge: {dataset.metadata.edge}\n"
                f"npts: {dataset.metadata.npts}\n"
                f"xmax: {dataset.metadata.xmax}\n"
                f"xmin: {dataset.metadata.xmin}"
            )
            dataset.blurb = f"Athena project file of {dataset.metadata.atsym} {dataset.metadata.edge} edge"

        else:
            dataset.peek = "file does not exist"
            dataset.blurb = "file purged from disk"


@build_sniff_from_prefix
class FEFFInput(Text):
    """
    FEFF input format
    """

    file_ext = "inp"

    MetadataElement(
        name="title_block",
        desc="Title block",
        readonly=True,
        visible=True,
    )

    def sniff_prefix(self, file_prefix: FilePrefix) -> bool:
        """
        Try to guess if the file is an FEFF input file.

        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('larch_pymatgen.inp')
        >>> FEFFInput().sniff(fname)
        True
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('larch_atoms.inp')
        >>> FEFFInput().sniff(fname)
        True
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('larch_potentials.inp')
        >>> FEFFInput().sniff(fname)
        True
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('larch_bad_atoms.txt')
        >>> FEFFInput().sniff(fname)
        False
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('larch_bad_potentials.txt')
        >>> FEFFInput().sniff(fname)
        False
        >>> from galaxy.datatypes.sniff import get_test_fname
        >>> fname = get_test_fname('Si.cif')
        >>> FEFFInput().sniff(fname)
        False
        """
        # pymatgen marks generated FEFF inputs, but user might also upload from another source
        if file_prefix.startswith("* This FEFF.inp file generated by pymatgen"):
            return True

        generator = file_prefix.line_iterator()
        try:
            line = next(generator).strip()
            while line is not None:
                if line == "POTENTIALS":
                    line = next(generator).strip()
                    if line[0] == "*":
                        words = line[1:].split()
                        if (words[0] in ["potential-index", "ipot"]) and (words[1] == "Z"):
                            return True
                    return False

                elif line == "ATOMS":
                    line = next(generator).strip()
                    if line[0] == "*":
                        words = line[1:].split()
                        if words[:4] == ["x", "y", "z", "ipot"]:
                            return True
                    return False

                else:
                    line = next(generator).strip()

        except StopIteration:
            return False

        return False

    def set_meta(self, dataset: "DatasetInstance", overwrite: bool = True, **kwd) -> None:
        """
        Extract metadata from TITLE
        """
        title_block = ""
        headers = get_headers(dataset.file_name, sep=None, comment_designator="*")
        for header in headers:
            if header and header[0] == "TITLE":
                title_block += " ".join(header[1:]) + "\n"

        dataset.metadata.title_block = title_block

    def set_peek(self, dataset: "DatasetInstance", **kwd) -> None:
        if not dataset.dataset.purged:
            dataset.peek = get_file_peek(dataset.file_name)
            dataset.info = dataset.metadata.title_block

        else:
            dataset.peek = "file does not exist"
            dataset.blurb = "file purged from disk"
