from loguru import logger

from src.core import settings
from src.rag.vector_db.vectorstore import get_retriever_instance
from src.utils import filter_non_header_documents, load_data


async def initialize_vector_store() -> bool:
    """
    Initialize and populate vector store if needed.

    Args:
        retriever: QdrantClientWrapper instance

    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        retriever = get_retriever_instance()
        raw_documents = load_data(settings.DATA_PATH)
        documents = filter_non_header_documents(raw_documents)

        await retriever.create_collection(
            collection_name=settings.COLLECTION, dimension=1024
        )

        doc_count = await retriever.count_documents(collection_name=settings.COLLECTION)
        logger.info(f"Current documents in vector store: {doc_count}")

        if doc_count == 0 or doc_count != len(documents):
            logger.warning("Document count mismatch or empty collection")
            logger.info("Loading documents into vector store...")

            settings.TOTAL_DOCUMENTS = len(documents)
            logger.info(f"Total documents to load: {settings.TOTAL_DOCUMENTS}")

            await retriever.upload_documents(
                collection_name=settings.COLLECTION,
                documents=documents,
                dense_instruction=settings.INSTRUCTION_DOC
            )

            new_count = await retriever.count_documents(collection_name=settings.COLLECTION)
            logger.success(f"Successfully loaded {new_count} documents")
        else:
            logger.info("Vector store is up to date")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize vector store: {e}")
        return False
