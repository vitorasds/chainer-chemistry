import os
import pickle
import ast
import numpy as np
import pandas as pd


import chainer
import h5py
from tqdm import tqdm
from pymatgen.core.structure import Structure


class MPDataset(chainer.dataset.DatasetMixin):
    """
    """

    def __init__(self, preprocessor):
        """
        """
        self.id_prop_data = None
        self.data = None
        self.mpid = []
        self.preprocessor = preprocessor

    def __len__(self):
        """
        """
        return len(self.data)

    def save_pickle(self, path):
        """
        """
        print("saving dataset into {}".format(path))
        with open(path, "wb") as file_:
            pickle.dump(self.data, file_)

    def load_pickle(self, path):
        """
        """
        print("loading dataset from {}".format(path))
        if os.path.exists(path) is False:
            print("Fail.")
            return False
        with open(path, "rb") as file_:
            self.data = pickle.load(file_)

        return True

    def _load_data_list(self, data_dir, target_list, is_stable=True):
        """Collect the label
        """
        # TODO: data_dirは今後はURLを指すようになる
        id_prop_data = pd.read_csv(os.path.join(
            data_dir, "property_data.csv"), index_col=0)
        stability_data = pd.read_csv(os.path.join(data_dir,
                                                  "stability_data.csv"),
                                     index_col=0,
                                     converters={3: ast.literal_eval})

        id_prop_data = id_prop_data.merge(stability_data, on="material_id")
        # drop data which has warnings
        if is_stable:
            n_warns = np.array([len(d) for d in id_prop_data["warnings"]])
            mask = n_warns == 0
            id_prop_data = id_prop_data[mask]

        # drop data which doesn't have fermi energy data
        # id_prop_data = id_prop_data[~np.isnan(id_prop_data["efermi"].values)]

        if "band_gap" in target_list:
            id_prop_data = id_prop_data[id_prop_data["band_gap"].values > 0]

        if "K_VRH" in target_list or "G_VRH" in target_list \
                or "poisson_ratio" in target_list:
            id_prop_data = id_prop_data[id_prop_data["K_VRH"] >= 1]
            id_prop_data = id_prop_data[id_prop_data["G_VRH"] >= 1]

        self.id_prop_data = id_prop_data

    def get_mp(self, data_dir, target_list, num_data=None, is_stable=True):
        """Download dataaset from Material Project dataset.

        Args:
            target_list (List): List of target labels.
            num_data (int): the number of data that we want to get
            is_stable (bool): If this value is true, load data that do not
                                have calculation warnings

        Returns:
            dataset, which is composed of `crystal object` and `target`
        """

        print("loading mp dataset from {}".format(data_dir))
        # TODO: is_stableは外で受け取る
        self._load_data_list(data_dir, target_list, is_stable)

        # TODO: data_dirはURLを指すようにする
        cif_data = h5py.File(os.path.join(data_dir, "cif_data.h5"), "r")

        data = self.id_prop_data
        if num_data is not None and num_data >= 0:
            data = data[0:num_data]

        self.data = list()
        data_length = len(data)
        for i in tqdm(range(data_length)):
            # get crystal object from CIF
            properties = self.id_prop_data.iloc[i]
            cif_id = properties["material_id"] + ".cif"
            if cif_id not in cif_data:
                continue
            crystal = Structure.from_str(cif_data[cif_id].value, "yaml")

            # prepare lebel
            target = properties[target_list].astype(np.float32)
            if np.isnan(target).any():
                continue
            # convert unit into /atom
            if "energy" in target:
                n_atom = crystal.num_sites
                target["energy"] = target["energy"] / n_atom
            # convert to log10
            if "K_VRH" in target:
                target["K_VRH"] = np.log10(target["K_VRH"])
            # convert to log10
            if "G_VRH" in target:
                target["G_VRH"] = np.log10(target["G_VRH"])

            self.data.append((crystal, target))
            self.mpid.append(properties["material_id"])

        return True

    def get_example(self, i):
        features = self.preprocessor.get_input_feature_from_crystal(
            self.data[i][0])
        return tuple((*features, self.data[i][1]))
