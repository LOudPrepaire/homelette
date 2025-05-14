import warnings
# Suppress warnings from homelette
warnings.filterwarnings("ignore", category=UserWarning, module="homelette")
from typing import Dict
import os
import yaml
from lib.msa import msa
from lib.alignment import Alignment
import homelette
import boto3
import logging
import json
import sys
import tempfile
import botocore.exceptions

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load configuration from YAML file
try:
    with open(os.path.join(os.getcwd(), "config.yaml"), "r") as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    logger.error("Configuration file 'config.yaml' not found in current directory.")
    sys.exit(1)
except yaml.YAMLError as e:
    logger.error(f"Error parsing config.yaml: {e}")
    sys.exit(1)

def record_seq_read(records: Dict) -> Dict:
    """Process sequence records into a dictionary."""
    seqs = {}
    for key, record in records.items():
        for rec in record:
            aas = "".join(aa.upper() for aa in rec.seq)
            seqs[f"{key}_{rec.name}"] = aas
    return seqs

def download_from_s3(local_file: str, bucket: str, object_key: str) -> None:
    """Download a file from S3."""
    s3 = boto3.client('s3')
    logger.info(f"Downloading s3://{bucket}/{object_key} to {local_file}")
    try:
        s3.download_file(bucket, object_key, local_file)
    except botocore.exceptions.ClientError as e:
        logger.error(f"Failed to download from S3: {e}")
        raise

def upload_to_s3(local_file: str, bucket: str, object_key: str) -> None:
    """Upload a file to S3."""
    s3 = boto3.client('s3')
    logger.info(f"Uploading {local_file} to s3://{bucket}/{object_key}")
    try:
        s3.upload_file(local_file, bucket, object_key)
    except botocore.exceptions.ClientError as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise

def align(tcr_cdr_light: str, tcr_cdr_heavy: str, species: str = "human") -> Dict:
    """Perform sequence alignment for given light and heavy chains."""
    try:
        align_result = msa(tcr_cdr_light, tcr_cdr_heavy, species)
        seqs = record_seq_read(align_result)

        target = f"{seqs['heavyChain_TargetSeq']}/{seqs['heavyChain_TargetSeq']}/" \
                 f"{seqs['lightChain_TargetSeq']}/{seqs['lightChain_TargetSeq']}"
        model = f"{seqs['heavyChain_ModelSeq']}/{seqs['heavyChain_ModelSeq']}/" \
                f"{seqs['lightChain_ModelSeq']}/{seqs['lightChain_ModelSeq']}"

        return {"TetraValent": target, "ModelAntibody": model}
    except KeyError as e:
        raise ValueError(f"Missing key in sequence data: {e}")
    except Exception as e:
        raise RuntimeError(f"Alignment error: {e}")

def model_generation(TetraValent: str, Model: str, output_dir: str, species: str = "human") -> str:
    """Generate a protein model based on alignment data."""
    try:
        aln = Alignment({"TetraValent": TetraValent, "Model-Antibody": Model})
        aln.get_sequence("TetraValent").annotate(seq_type="sequence")

        model_config = config["Models"]
        if species not in ['human', 'mouse']:
            raise ValueError(f"Invalid species '{species}'. Supported: 'human', 'mouse'")

        aln.get_sequence("Model-Antibody").annotate(
            seq_type="structure",
            pdb_code=os.path.join(os.getcwd(), model_config[f"{species}_model"]),
            begin_res="1",
            begin_chain="B",
            end_res="218",
            end_chain="C"
        )

        routine = homelette.routines.Routine_automodel_default(
            alignment=aln,
            target="TetraValent",
            templates=["Model-Antibody"],
            tag=os.path.join(output_dir, "model")
        )
        routine.generate_models()

        expected_file = os.path.join(output_dir, "model_1.pdb")
        if not os.path.exists(expected_file):
            raise FileNotFoundError(f"Model file not generated at {expected_file}")

        return expected_file
    except Exception as e:
        raise RuntimeError(f"Model generation error: {e}")

def main(s3_input_key: str, s3_output_key: str, s3_bucket: str) -> None:
    """Main function to process sequence data, align, generate model, and upload to S3."""
    try:
        if not all([s3_input_key, s3_bucket, s3_output_key]):
            raise ValueError("All command-line arguments (INPUT_KEY, BUCKET, OUTPUT_KEY) must be provided.")

        with tempfile.TemporaryDirectory() as temp_dir:
            file = os.path.join(temp_dir, "sequence.json")
            download_from_s3(file, s3_bucket, s3_input_key)
            logger.info("File downloaded successfully")

            with open(file, 'r') as f:
                protein_data = json.load(f)
            if not all(k in protein_data for k in ['light_sequence', 'heavy_sequence']):
                raise ValueError("JSON data must contain 'light_sequence' and 'heavy_sequence' keys")

            alignment_data = align(
                tcr_cdr_light=protein_data['light_sequence'],
                tcr_cdr_heavy=protein_data['heavy_sequence']
            )
            logger.info("Alignment completed")

            file_path = model_generation(
                TetraValent=alignment_data['TetraValent'],
                Model=alignment_data['ModelAntibody'],
                output_dir=temp_dir
            )
            logger.info(f"Model generated at {file_path}")

            upload_to_s3(file_path, s3_bucket, s3_output_key)
            logger.info("File uploaded successfully")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python app.py <INPUT> <OUTPUT> <BUCKET>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])