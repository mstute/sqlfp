from typing import Literal, final

__version__: str

Dialect = Literal[
    "generic",
    "ansi",
    "mysql",
    "mariadb",
    "postgresql",
    "postgres",
    "sqlite",
    "mssql",
    "oracle",
]

@final
class NormalizeResult:
    """Result of a SQL normalization and fingerprinting operation."""

    @property
    def normalized(self) -> str:
        """The normalized SQL with literals replaced by placeholders."""
        ...

    @property
    def hash(self) -> str:
        """SHA-256 hex digest of the normalized SQL."""
        ...

    @property
    def original(self) -> str:
        """The original SQL string as provided."""
        ...

    @property
    def params(self) -> list[str]:
        """Extracted literal values in order of appearance."""
        ...

    def __repr__(self) -> str: ...

def normalize(
    sql: str,
    dialect: Dialect = "generic",
    placeholder: str = "?",
) -> NormalizeResult:
    """Normalize a SQL statement and return its fingerprint.

    Args:
        sql: The SQL statement to normalize.
        dialect: The SQL dialect to use for parsing. Defaults to ``"generic"``.
        placeholder: The string to replace literal values with. Defaults to ``"?"``.

    Returns:
        A :class:`NormalizeResult` containing the normalized SQL, its SHA-256
        hash, the original SQL, and the extracted parameter values.

    Raises:
        ValueError: If the dialect is not supported or the SQL cannot be parsed.

    Example::

        import sqlfp

        result = sqlfp.normalize(
            "SELECT * FROM users WHERE id = 42",
            dialect="postgres",
        )
        print(result.hash)        # SHA-256 of the normalized form
        print(result.normalized)  # SELECT * FROM users WHERE id = ?
        print(result.params)      # ['42']
    """
    ...
