import pytest
import httpx
from unittest.mock import Mock

from src.models.interfaces import IConfig
from src.services.timeout_configurator import TimeoutConfigurator


class TestTimeoutConfigurator:
    """Тесты для TimeoutConfigurator"""

    @pytest.fixture
    def mock_config(self):
        """Создает мок конфигурации"""
        config = Mock(spec=IConfig)
        config.timeout_connect = 5.0
        config.timeout_read = 30.0
        config.timeout_write = 30.0
        config.timeout_pool = 10.0
        return config

    @pytest.fixture
    def timeout_configurator(self, mock_config):
        """Создает экземпляр TimeoutConfigurator с моком конфигурации"""
        return TimeoutConfigurator(mock_config)

    def test_initialization(self, mock_config):
        """Тест инициализации TimeoutConfigurator"""
        # Act
        configurator = TimeoutConfigurator(mock_config)

        # Assert
        assert configurator.config == mock_config

    def test_create_timeout_config_default_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с множителем по умолчанию"""
        # Act
        timeout = timeout_configurator.create_timeout_config()

        # Assert
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == mock_config.timeout_connect * 1
        assert timeout.read == mock_config.timeout_read * 1
        assert timeout.write == mock_config.timeout_write * 1
        assert timeout.pool == mock_config.timeout_pool * 1

    def test_create_timeout_config_with_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с кастомным множителем"""
        # Arrange
        multiplier = 3

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier

    def test_create_timeout_config_zero_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с нулевым множителем"""
        # Arrange
        multiplier = 0

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier

    def test_create_timeout_config_negative_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с отрицательным множителем"""
        # Arrange
        multiplier = -2

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier

    def test_create_timeout_config_float_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с дробным множителем"""
        # Arrange
        multiplier = 1.5

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier

    def test_create_timeout_config_different_config_values(self):
        """Тест создания конфигурации таймаута с разными значениями в конфиге"""
        # Arrange
        mock_config = Mock(spec=IConfig)
        mock_config.timeout_connect = 2.5
        mock_config.timeout_read = 15.0
        mock_config.timeout_write = 20.0
        mock_config.timeout_pool = 5.0

        configurator = TimeoutConfigurator(mock_config)
        multiplier = 2

        # Act
        timeout = configurator.create_timeout_config(multiplier)

        # Assert
        assert timeout.connect == 2.5 * multiplier  # 5.0
        assert timeout.read == 15.0 * multiplier    # 30.0
        assert timeout.write == 20.0 * multiplier   # 40.0
        assert timeout.pool == 5.0 * multiplier     # 10.0

    def test_create_timeout_config_verify_timeout_object(self, timeout_configurator):
        """Тест проверки свойств объекта таймаута"""
        # Act
        timeout = timeout_configurator.create_timeout_config(2)

        # Assert
        assert hasattr(timeout, 'connect')
        assert hasattr(timeout, 'read')
        assert hasattr(timeout, 'write')
        assert hasattr(timeout, 'pool')

        # Проверяем что это именно httpx.Timeout
        assert isinstance(timeout, httpx.Timeout)

    def test_create_timeout_config_multiple_calls(self, timeout_configurator, mock_config):
        """Тест множественных вызовов create_timeout_config"""
        # Act
        timeout1 = timeout_configurator.create_timeout_config(1)
        timeout2 = timeout_configurator.create_timeout_config(2)
        timeout3 = timeout_configurator.create_timeout_config(0.5)

        # Assert
        assert timeout1.connect == mock_config.timeout_connect * 1
        assert timeout2.connect == mock_config.timeout_connect * 2
        assert timeout3.connect == mock_config.timeout_connect * 0.5

        assert timeout1.read == mock_config.timeout_read * 1
        assert timeout2.read == mock_config.timeout_read * 2
        assert timeout3.read == mock_config.timeout_read * 0.5

    def test_create_timeout_config_edge_cases(self, timeout_configurator, mock_config):
        """Тест граничных случаев для множителя"""
        test_cases = [
            (1, "единичный множитель"),
            (0, "нулевой множитель"),
            (-1, "отрицательный множитель"),
            (100, "большой множитель"),
            (0.001, "очень маленький множитель"),
            (1.0, "дробный единичный множитель"),
        ]

        for multiplier, description in test_cases:
            # Act
            timeout = timeout_configurator.create_timeout_config(multiplier)

            # Assert
            assert timeout.connect == mock_config.timeout_connect * multiplier, f"Ошибка для {description}"
            assert timeout.read == mock_config.timeout_read * multiplier, f"Ошибка для {description}"
            assert timeout.write == mock_config.timeout_write * multiplier, f"Ошибка для {description}"
            assert timeout.pool == mock_config.timeout_pool * multiplier, f"Ошибка для {description}"

    def test_create_timeout_config_with_none_values(self):
        """Тест создания конфигурации таймаута с None значениями в конфиге"""
        # Arrange
        mock_config = Mock(spec=IConfig)
        mock_config.timeout_connect = None
        mock_config.timeout_read = None
        mock_config.timeout_write = None
        mock_config.timeout_pool = None

        configurator = TimeoutConfigurator(mock_config)

        # Act
        timeout = configurator.create_timeout_config(2)

        # Assert
        assert timeout.connect is None
        assert timeout.read is None
        assert timeout.write is None
        assert timeout.pool is None

    def test_create_timeout_config_with_mixed_values(self):
        """Тест создания конфигурации таймаута со смешанными значениями в конфиге"""
        # Arrange
        mock_config = Mock(spec=IConfig)
        mock_config.timeout_connect = 5.0
        mock_config.timeout_read = None
        mock_config.timeout_write = 0.0
        mock_config.timeout_pool = 10.0

        configurator = TimeoutConfigurator(mock_config)
        multiplier = 3

        # Act
        timeout = configurator.create_timeout_config(multiplier)

        # Assert
        assert timeout.connect == 5.0 * multiplier  # 15.0
        assert timeout.read is None
        assert timeout.write == 0.0 * multiplier    # 0.0
        assert timeout.pool == 10.0 * multiplier    # 30.0

    def test_create_timeout_config_verify_timeout_usage(self, timeout_configurator):
        """Тест проверки что созданный таймаут может быть использован в httpx"""
        # Act
        timeout = timeout_configurator.create_timeout_config(1)

        # Assert - проверяем что объект совместим с httpx
        assert isinstance(timeout, httpx.Timeout)

        # Можем создать клиента с этим таймаутом
        try:
            client = httpx.Client(timeout=timeout)
            client.close()
        except Exception:
            pytest.fail("Созданный таймаут несовместим с httpx")

    def test_create_timeout_config_string_representation(self, timeout_configurator):
        """Тест строкового представления созданного таймаута"""
        # Act
        timeout = timeout_configurator.create_timeout_config(2)

        # Assert
        str_repr = str(timeout)
        assert "Timeout" in str_repr
        # Проверяем что все таймауты присутствуют в строковом представлении
        assert "connect" in str_repr.lower()
        assert "read" in str_repr.lower()
        assert "write" in str_repr.lower()
        assert "pool" in str_repr.lower()

    def test_create_timeout_config_with_very_large_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с очень большим множителем"""
        # Arrange
        multiplier = 1000000

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier

    def test_create_timeout_config_with_very_small_multiplier(self, timeout_configurator, mock_config):
        """Тест создания конфигурации таймаута с очень маленьким множителем"""
        # Arrange
        multiplier = 0.0001

        # Act
        timeout = timeout_configurator.create_timeout_config(multiplier)

        # Assert
        assert timeout.connect == mock_config.timeout_connect * multiplier
        assert timeout.read == mock_config.timeout_read * multiplier
        assert timeout.write == mock_config.timeout_write * multiplier
        assert timeout.pool == mock_config.timeout_pool * multiplier