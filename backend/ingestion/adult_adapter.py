"""
Ticket #5: Middleman to standardized an input dataset -> pandas dataframe
As per ticket:
    Adult Dataset -> Adult Adapter -> Standard Pandas DataFrame -> Pipeline
"""
import pandas as pd
from backend.ingestion.csv_loader import CSVLoadError, load_csv

ADULT_COLUMNS = [
    "age",
    "workclass",
    "fnlwgt",
    "education",
    "education_num",
    "marital_status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital_gain",
    "capital_loss",
    "hours_per_week",
    "native_country",
    "income",
]

# Columns the pipeline expects to be able to do arithmetics.
ADULT_NUMERIC_COLUMNS = [
    "age",
    "fnlwgt",
    "education_num",
    "capital_gain",
    "capital_loss",
    "hours_per_week",
]
ADULT_MISSING_VALUE = "?" # ? represents missing fields; I'm treating them as NaN's
_METADATA_PREFIX = "|" # Metadata begins with this... everything else is data
_ENCODING = "utf-8-sig" 

def load_adult(file_path: str) -> pd.DataFrame:
    """input adult.data or adult.test -> output standardized DataFrame.
    edge cases checked:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file is not readable.
        CSVLoadError: If the file is empty, cannot be parsed, or does not have
            the expected Adult column layout.
    """
    df = load_csv(
        file_path,
        header=None,
        names=ADULT_COLUMNS,
        skipinitialspace=True,
        na_values=ADULT_MISSING_VALUE,
        skip_blank_lines=True,
        encoding=_ENCODING,
    )

    if str(df.iloc[0]["age"]).lstrip().startswith(_METADATA_PREFIX):
        df = df.iloc[1:].reset_index(drop=True)
        if df.empty:
            raise CSVLoadError(
                f"{file_path} contains only the UCI metadata line, no data rows."
            )

    if not pd.api.types.is_object_dtype(df["income"]):
        raise CSVLoadError(
            f"Expected text income labels in {file_path}, found dtype "
            f"'{df['income'].dtype}'. The file does not have the 15-column UCI "
            f"Adult layout: {', '.join(ADULT_COLUMNS)}."
        )

    # check again after stripping so a padded "? " treating it as missing too.
    for column in df.select_dtypes(include="object").columns:
        stripped = df[column].str.strip()
        df[column] = stripped.mask(stripped == ADULT_MISSING_VALUE)

    for column in ADULT_NUMERIC_COLUMNS:
        if pd.api.types.is_object_dtype(df[column]):
            try:
                df[column] = pd.to_numeric(df[column])
            except (TypeError, ValueError) as exc:
                raise CSVLoadError(
                    f"Column '{column}' in {file_path} contains non-numeric "
                    f"values: {exc}"
                ) from exc

    df["income"] = df["income"].str.rstrip(".")

    return df