import json
import tiktoken
from typing import List, Dict


def load_data(path: str) -> List[Dict]:
    """
    Load data from a JSON file and return a list of dictionaries.
    """
    with open(path, "r") as f:
        data = json.load(f)
    return data


def filter_non_header_documents(document_list: List[Dict]) -> List[Dict]:
    """
    Filter documents to include only those where is_header is False.

    Args:
        document_list: List of document dictionaries containing 'is_header' field

    Returns:
        List[Dict]: Filtered list containing only non-header documents

    Example:
        >>> documents = [
        ...     {'id': 1, 'is_header': True, 'content': 'Header text'},
        ...     {'id': 2, 'is_header': False, 'content': 'Regular content'},
        ...     {'id': 3, 'is_header': False, 'content': 'Another regular content'}
        ... ]
        >>> filtered = filter_non_header_documents(documents)
        >>> len(filtered)
        2
        >>> filtered[0]['id']
        2
    """
    return [doc for doc in document_list if doc.get('is_header') is False]



def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in a given text using the specified model.

    Args:
        text (str): The input text to be tokenized.
        model_name (str): The name of the model to use for tokenization.
    Returns:
        int: The number of tokens in the input text.
    """
    encoding = tiktoken.encoding_for_model(model_name)
    return len(encoding.encode(text))