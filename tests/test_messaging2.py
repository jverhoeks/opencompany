import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from opencompany.company.messaging import deliver_message

# Создаем фейковые объекты "Персона", чтобы не использовать настоящую БД
class FakePersona:
    def __init__(self, id, name, role, status="active"):
        self.id = id
        self.name = name
        self.role = role
        self.status = status

@pytest.mark.asyncio
async def test_deliver_message_sender_not_found():
    """Тест 1: Отправитель не найден (покрывает строку 17)"""
    # Мокаем сессию БД
    mock_session = AsyncMock()
    mock_session.get.return_value = None # БД никого не нашла
    
    with patch("opencompany.company.messaging.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        result = await deliver_message("sender-123", "recipient-456", "Hello")
        
        assert result == "Error: sender 'sender-123' not found"

@pytest.mark.asyncio
async def test_deliver_message_recipient_not_found():
    """Тест 2: Получатель не найден (покрывает строку 19)"""
    mock_session = AsyncMock()
    sender = FakePersona("sender-123", "Alice", "Manager")
    
    # Имитируем, что отправитель найден, а получатель - нет
    async def mock_get(model, id):
        if id == "sender-123": return sender
        return None
        
    mock_session.get = mock_get
    
    with patch("opencompany.company.messaging.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        result = await deliver_message("sender-123", "recipient-456", "Hello")
        
        assert result == "Error: recipient 'recipient-456' not found"

@pytest.mark.asyncio
async def test_deliver_message_recipient_inactive():
    """Тест 3: Получатель не активен (покрывает строку 21)"""
    mock_session = AsyncMock()
    sender = FakePersona("sender-123", "Alice", "Manager")
    recipient = FakePersona("recipient-456", "Bob", "Worker", status="sleeping")
    
    async def mock_get(model, id):
        if id == "sender-123": return sender
        if id == "recipient-456": return recipient
        return None
        
    mock_session.get = mock_get
    
    with patch("opencompany.company.messaging.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        result = await deliver_message("sender-123", "recipient-456", "Hello")
        
        assert result == "Error: recipient 'recipient-456' is sleeping"

@pytest.mark.asyncio
@patch("opencompany.company.engine._spawn_persona_task")
async def test_deliver_message_success(mock_spawn_task):
    """Тест 4: Успешная доставка (покрывает строки 23-35)"""
    mock_session = AsyncMock()
    sender = FakePersona("sender-123", "Alice", "Manager")
    recipient = FakePersona("recipient-456", "Bob", "Worker", status="active")
    
    async def mock_get(model, id):
        if id == "sender-123": return sender
        if id == "recipient-456": return recipient
        return None
        
    mock_session.get = mock_get
    
    with patch("opencompany.company.messaging.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        result = await deliver_message("sender-123", "recipient-456", "Test message")
        
        # Проверяем, что вернулось правильное сообщение
        assert result == "Message delivered to Bob (recipient-456)"
        
        # Проверяем, что функция _spawn_persona_task действительно была вызвана
        mock_spawn_task.assert_called_once()
        
        # Проверяем, что в нее передали правильный текст
        args, _ = mock_spawn_task.call_args
        assert "Message from Alice (Manager):" in args[1]
        assert "Test message" in args[1]