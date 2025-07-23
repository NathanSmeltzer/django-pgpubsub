"""Tests for payload drift handling in LockableNotificationProcessor"""
import json
import pytest
from unittest.mock import Mock
from django.db import transaction

from pgpubsub.compatibility import Notify
from pgpubsub.listen import LockableNotificationProcessor
from pgpubsub.models import Notification
from pgpubsub.tests.channels import AuthorTriggerChannel
from pgpubsub.tests.models import Author


def create_test_processor(pg_notification):
    """Helper to create a properly configured test processor"""
    processor = LockableNotificationProcessor.__new__(LockableNotificationProcessor)
    processor.notification = pg_notification
    processor.channel_cls = AuthorTriggerChannel
    processor.callbacks = []
    processor.connection_wrapper = Mock()

    # Mock _execute to avoid running actual callbacks
    processor._execute = Mock()

    return processor


@pytest.mark.django_db(transaction=True)
def test_process_by_id_success():
    """Test that process_by_id can find notification when exact payload matching fails"""
    # Create an author to work with
    author = Author.objects.create(name='Test Author', age=30)

    # Clear any auto-generated notifications from the Author creation
    Notification.objects.all().delete()

    # Use the actual channel name from AuthorTriggerChannel
    channel_name = AuthorTriggerChannel.listen_safe_name()

    # Create a notification with original payload
    original_payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {
            'id': author.id,
            'name': 'Test Author',
            'age': 30,
            'active': True
        },
        'old': {
            'id': author.id,
            'name': 'Old Name',
            'age': 25,
            'active': True
        }
    }

    notification = Notification.objects.create(
        channel=channel_name,
        payload=original_payload
    )

    # Create a Postgres notification with drifted payload (age changed)
    drifted_payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {
            'id': author.id,
            'name': 'Test Author',
            'age': 35,  # This changed, causing payload mismatch
            'active': True
        },
        'old': {
            'id': author.id,
            'name': 'Old Name',
            'age': 30,  # This also changed
            'active': True
        }
    }

    # Create mock Postgres notification
    pg_notification = Mock(spec=Notify)
    pg_notification.payload = json.dumps(drifted_payload)
    pg_notification.channel = channel_name
    pg_notification.pid = 12345

    # Create processor with proper setup
    processor = create_test_processor(pg_notification)

    # Count notifications before
    initial_count = Notification.objects.count()
    assert initial_count == 1

    # Call process_by_id method within transaction context (as it would be in production)
    with transaction.atomic():
        processor.process_by_id()

    # Verify _execute was called
    processor._execute.assert_called_once()

    # Verify notification was processed and deleted
    final_count = Notification.objects.count()
    assert final_count == 0


@pytest.mark.django_db(transaction=True)
def test_process_by_id_no_matching_id():
    """Test process_by_id when no notification exists for the given ID"""
    channel_name = AuthorTriggerChannel.listen_safe_name()

    # Create a Postgres notification for non-existent object
    payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {
            'id': 99999,  # Non-existent ID
            'name': 'Non-existent Author',
            'age': 30
        },
        'old': {
            'id': 99999,
            'name': 'Old Name',
            'age': 25
        }
    }

    pg_notification = Mock(spec=Notify)
    pg_notification.payload = json.dumps(payload)
    pg_notification.channel = channel_name
    pg_notification.pid = 12345

    processor = create_test_processor(pg_notification)

    # Should not raise exception, should handle gracefully
    processor.process_by_id()

    # _execute should not be called since no notification found
    processor._execute.assert_not_called()

    # No notifications should be processed
    assert Notification.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_process_by_id_invalid_payload():
    """Test process_by_id with invalid JSON payload"""
    channel_name = AuthorTriggerChannel.listen_safe_name()

    pg_notification = Mock(spec=Notify)
    pg_notification.payload = "invalid json"
    pg_notification.channel = channel_name
    pg_notification.pid = 12345

    processor = create_test_processor(pg_notification)

    # Should handle gracefully without crashing
    processor.process_by_id()

    # _execute should not be called due to invalid payload
    processor._execute.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_process_by_id_missing_id_in_payload():
    """Test process_by_id when payload is missing 'new.id' field"""
    channel_name = AuthorTriggerChannel.listen_safe_name()

    payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {
            'name': 'Test Author',  # Missing 'id' field
            'age': 30
        },
        'old': {
            'name': 'Old Name',
            'age': 25
        }
    }

    pg_notification = Mock(spec=Notify)
    pg_notification.payload = json.dumps(payload)
    pg_notification.channel = channel_name
    pg_notification.pid = 12345

    processor = create_test_processor(pg_notification)

    # Should handle gracefully
    processor.process_by_id()

    # _execute should not be called due to missing ID
    processor._execute.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_process_by_id_with_multiple_notifications():
    """Test process_by_id when multiple notifications exist for same ID"""
    author = Author.objects.create(name='Test Author', age=30)

    # Clear any auto-generated notifications from the Author creation
    Notification.objects.all().delete()

    channel_name = AuthorTriggerChannel.listen_safe_name()

    # Create multiple notifications for same author
    for i in range(3):
        Notification.objects.create(
            channel=channel_name,
            payload={
                'app': 'tests',
                'model': 'Author',
                'new': {'id': author.id, 'name': f'Name {i}', 'age': 30 + i},
                'old': {'id': author.id, 'name': 'Old Name', 'age': 25}
            }
        )

    payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {
            'id': author.id,
            'name': 'Drifted Name',  # Different from stored notifications
            'age': 50  # Different age
        },
        'old': {
            'id': author.id,
            'name': 'Old Name',
            'age': 25
        }
    }

    pg_notification = Mock(spec=Notify)
    pg_notification.payload = json.dumps(payload)
    pg_notification.channel = channel_name
    pg_notification.pid = 12345

    processor = create_test_processor(pg_notification)

    initial_count = Notification.objects.count()
    assert initial_count == 3

    # Should process one notification
    # Call process_by_id method within transaction context (as it would be in production)
    with transaction.atomic():
        processor.process_by_id()

    # _execute should be called once
    processor._execute.assert_called_once()

    final_count = Notification.objects.count()
    assert final_count == 2  # One less than before


@pytest.mark.django_db(transaction=True)
def test_integration_exact_payload_vs_id_fallback():
    """Integration test showing fallback from exact payload to ID matching"""
    author = Author.objects.create(name='Test Author', age=30)

    # Clear any auto-generated notifications from the Author creation
    Notification.objects.all().delete()

    channel_name = AuthorTriggerChannel.listen_safe_name()

    # Create notification with original data
    original_payload = {
        'app': 'tests',
        'model': 'Author',
        'new': {'id': author.id, 'name': 'Test Author', 'age': 30},
        'old': {'id': author.id, 'name': 'Old Name', 'age': 25}
    }

    notification = Notification.objects.create(
        channel=channel_name,
        payload=original_payload
    )

    # Test ID fallback with drifted payload
    drifted_payload = original_payload.copy()
    drifted_payload['new']['age'] = 35  # Changed age

    pg_notification_drift = Mock(spec=Notify)
    pg_notification_drift.payload = json.dumps(drifted_payload)
    pg_notification_drift.channel = channel_name
    pg_notification_drift.pid = 12346

    processor_drift = create_test_processor(pg_notification_drift)

    # ID fallback should find the notification
    assert Notification.objects.count() == 1
    # Call process_by_id method within transaction context (as it would be in production)
    with transaction.atomic():
        processor_drift.process_by_id()

    # Should have been processed
    processor_drift._execute.assert_called_once()
    assert Notification.objects.count() == 0
