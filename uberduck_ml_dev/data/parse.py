__all__ = ["STANDARD_MULTISPEAKER", "STANDARD_SINGLESPEAKER", "VCTK"]


import os
import numpy as np
import sqlite3
import uuid
from pathlib import PosixPath
from tqdm import tqdm
from pathlib import Path
import os
import pandas as pd
import json
from .cache import CACHE_LOCATION

STANDARD_MULTISPEAKER = "standard-multispeaker"
STANDARD_SINGLESPEAKER = "standard-singlespeaker"
VCTK = "vctk"


def _cache_filelists(folder, fmt, conn, dataset_name: str = None):
    """
    records a filelist into the speaker cache
    """
    if fmt == STANDARD_MULTISPEAKER:
        _parse_ms(root=folder, dataset_name=dataset_name)
    if fmt == STANDARD_SINGLESPEAKER:
        _parse_ss(
            conn=conn,
            root=folder,
            speaker_name=dataset_name,
            dir_path=folder,
            dataset_name=dataset_name,
        )
    if fmt == VCTK:
        raise


def _add_speaker_to_db(
    filelist_path: str,
    speaker_name: str,
    speaker_id=None,
    dir_path: str = None,
    rel_path: str = None,
    dataset_name: str = None,
    conn=None,
):
    """
    filelist: the path of the filelist being added
    speaker_name: the name of the speaker
    dir_path: the path of the data repository containing the filelist
    rel_path: the path of the wavs within the repository
    dataset_name: the name of the dataset
    """
    uuid_ = uuid.uuid4()
    if conn is None:
        conn = sqlite3.connect(str(CACHE_LOCATION_EXP))
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO FILELISTS VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid_),
            filelist_path,
            speaker_name,
            speaker_id,
            dir_path,
            rel_path,
            dataset_name,
        ),
    )
    conn.commit()
    cursor.close()


def _parse_ms(root: str, dataset_name: str, conn):
    speakers = os.listdir(root)
    for speaker in tqdm(speakers):
        speaker_path = Path(root) / Path(speaker)
        if not path.is_dir() or path.parts[-1].startswith("."):
            continue
        _parse_ss(
            root=speaker_path,
            speaker_name=speaker,
            speaker_id=None,
            dir_path=root,
            dataset_name=dataset_name,
            rel_path=speaker,
            conn=conn,
        )


def _parse_ss(
    conn,
    root: str,
    speaker_name: str,
    speaker_id=None,
    dir_path: str = None,
    dataset_name: str = None,
    rel_path="",
):
    files = os.listdir(root)
    filelist_paths = [f for f in files if f.endswith(".txt")]
    for filelist_path in filelist_paths:
        _add_speaker_to_db(
            filelist_path=filelist_path,
            speaker_name=speaker_name,
            speaker_id=speaker_id,
            dir_path=root,
            dataset_name=dataset_name,
            rel_path=rel_path,
            conn=conn,
        )


def _generate_filelist(config_path, conn, out):

    with open(config_path) as f:
        filelist_config = json.load(f)
    speaker_id = 0
    save_path = Path(out)
    exp_path = Path(os.path.join(*save_path.parts[:-1]))
    if not os.path.exists(exp_path):
        exp_path.mkdir(parents=True)
    with open(save_path, "w") as f_out:
        for filelist in filelist_config["filelists"]:
            uuid = filelist["uuid"]
            dir_path = filelist["dir_path"]
            cursor = conn.cursor()
            cursor.execute(
                "SELECT dir_path,rel_path,filelist_path FROM FILELISTS WHERE uuid = :uuid",
                {"uuid": uuid},
            )
            results = cursor.fetchall()
            assert len(results) == 1
            in_path = Path(os.path.join(*results[0]))
            with (in_path).open("r") as txn_f:
                transcriptions = txn_f.readlines()
            for line in transcriptions:
                line = line.strip("\n")
                try:
                    line_path, line_txn, *_ = line.split("|")
                except Exception as e:
                    print(e)
                    print(line)
                    raise
                out_path = os.path.join(
                    *([dir_path] + list(results[0][1:2]) + [line_path])
                )
                f_out.write(f"{out_path}|{line_txn}|{speaker_id}\n")
            speaker_id += 1


def _write_db_to_csv(conn, output_path):
    cursor = conn.cursor()
    query = cursor.execute("SELECT * From FILELISTS")

    cols = [column[0] for column in query.description]
    results = pd.DataFrame.from_records(data=query.fetchall(), columns=cols)
    results.to_csv(output_path, header=True)
    cursor.close()
