"""What every data source provides."""

from abc import ABC, abstractmethod
from typing import ClassVar

from minitela.protocol.tags import Register

Values = dict[Register, int | str]


class Source(ABC):
    """Reads one kind of system state and maps it to registers of the factory layout.

    The service calls `read()` every `interval` seconds and writes only the values that
    changed, so a source can be read often even if its values rarely change.
    """

    name: ClassVar[str]
    interval: ClassVar[float]

    @abstractmethod
    def read(self) -> Values: ...
