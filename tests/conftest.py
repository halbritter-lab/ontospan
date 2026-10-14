import pytest
from builders import sample

from ontospan.models import AnnotatedDocument


@pytest.fixture
def sample_unit() -> AnnotatedDocument:
    return sample()
