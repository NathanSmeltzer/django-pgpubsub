import datetime
from unittest.mock import patch

from django.db import connection
from django.db.transaction import atomic
from django.db.migrations.recorder import MigrationRecorder
import pytest

from pgpubsub.listen import (
    process_notifications,
    listen,
)
from pgpubsub.models import Notification
from pgpubsub.notify import process_stored_notifications
from pgpubsub.tests.channels import (
    AuthorTriggerChannel,
    MediaTriggerChannel,
)
from pgpubsub.tests.connection import simulate_listener_does_not_receive_notifications
from pgpubsub.tests.listeners import post_reads_per_date_cache
from pgpubsub.tests.models import Author, Media, Post


@pytest.mark.django_db(transaction=True)
def test_post_fetch_notify(pg_connection):
    author = Author.objects.create(name='Billy')
    Notification.from_channel(channel=AuthorTriggerChannel).get()
    assert 1 == len(pg_connection.notifies)
    today = datetime.date.today()
    post = Post.objects.create(
        author=author, content='first post', date=today)
    assert post_reads_per_date_cache[today] == {}
    Post.fetch(post.pk)
    assert 1 == Notification.objects.count()
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    process_notifications(pg_connection)
    assert post_reads_per_date_cache[today] == {post.pk: 1}
    assert 0 == Notification.objects.count()


@pytest.mark.django_db(transaction=True)
def test_author_insert_notify(pg_connection):
    author = Author.objects.create(name='Billy')
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(
        channel=AuthorTriggerChannel).get()
    assert 'old' in stored_notification.payload
    assert 'new' in stored_notification.payload
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.count()
    post = Post.objects.last()
    assert post.author == author

@pytest.mark.django_db(transaction=True)
def test_process_notifications_handles_non_json_payloads(pg_connection):
    author = Author.objects.create(name='Billy')
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(
        channel=AuthorTriggerChannel).get()
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {Notification._meta.db_table} SET payload = to_json(payload::text)")

    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.count()
    post = Post.objects.last()
    assert post.author == author

@pytest.mark.django_db(transaction=True)
def test_author_insert_notify_in_transaction(pg_connection):
    with atomic():
        author = Author.objects.create(name='Billy')
    pg_connection.poll()
    assert 1 == len(pg_connection.notifies)
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 1 == Post.objects.count()
    post = Post.objects.last()
    assert post.author == author


@pytest.mark.django_db(transaction=True)
def test_author_insert_notify_transaction_rollback(pg_connection):
    class TestException(Exception):
        pass

    try:
        with atomic():
            Author.objects.create(name='Billy')
            raise TestException
    except TestException:
        pass

    # Notifications are only sent when the transaction commits
    pg_connection.poll()
    assert not pg_connection.notifies
    assert not Author.objects.exists()
    assert not Post.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_author_bulk_insert_notify(pg_connection):
    authors = [Author(name='Billy'), Author(name='Craig')]
    with atomic():
        authors = Author.objects.bulk_create(authors)

    # TODO: Understand why pg_connection.poll() is only
    # necessary when we invoke a notification inside
    # a transaction (which happens in a bulk_create).
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    assert not Post.objects.exists()
    process_notifications(pg_connection)
    assert 2 == Post.objects.count()
    post_authors = Post.objects.values_list('author_id', flat=True)
    assert [author.pk for author in authors] == list(post_authors)


@pytest.mark.django_db(transaction=True)
def test_process_stored_notifications(pg_connection):
    Author.objects.create(name='Billy')
    Author.objects.create(name='Billy2')
    assert 2 == len(pg_connection.notifies)
    assert 2 == Notification.objects.count()
    assert 0 == Post.objects.count()
    simulate_listener_does_not_receive_notifications(pg_connection)
    process_stored_notifications()
    pg_connection.poll()
    # One notification for each lockable channel
    assert 5 == len(pg_connection.notifies)
    process_notifications(pg_connection)
    assert 0 == Notification.objects.count()
    assert 2 == Post.objects.count()


@pytest.mark.django_db(transaction=True)
def test_recover_notifications(pg_connection):
    Author.objects.create(name='Billy')
    Author.objects.create(name='Billy2')
    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)
    assert 2 == Notification.objects.count()
    assert 0 == Post.objects.count()
    simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 0 == Notification.objects.count()
    assert 2 == Post.objects.count()

@pytest.mark.django_db(transaction=True)
def test_recover_multiple_notifications(pg_connection):
    ENTITIES_COUNT = 5
    for i in range(ENTITIES_COUNT):
        Author.objects.create(name=f'Billy{i}')
    pg_connection.poll()
    assert ENTITIES_COUNT == len(pg_connection.notifies)
    assert ENTITIES_COUNT == Notification.objects.count()
    assert 0 == Post.objects.count()
    simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 0 == Notification.objects.count()
    assert ENTITIES_COUNT == Post.objects.count()


def _create_notification_that_cannot_be_processed():
    notification = Notification.objects.last()
    notification.payload.pop('app', None)
    notification.pk = None
    notification.save()


@pytest.mark.django_db(transaction=True)
def test_recover_notifications_after_exception(pg_connection):
    author = Author.objects.create(name='Billy')
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name='Billy2')

    pg_connection.poll()
    assert 2 == len(pg_connection.notifies)

    assert 3 == Notification.objects.count()
    assert 0 == Post.objects.count()

    simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert 1 == Notification.objects.count()
    assert 2 == Post.objects.count()

@pytest.mark.django_db(transaction=True)
def test_recover_multiple_notifications_after_exception(pg_connection):
    Author.objects.create(name=f'Billy_1')
    Author.objects.create(name=f'Billy_2')
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name=f'Billy_3')
    _create_notification_that_cannot_be_processed()
    _create_notification_that_cannot_be_processed()
    _create_notification_that_cannot_be_processed()
    Author.objects.create(name=f'Billy_4')
    Author.objects.create(name=f'Billy_5')

    GOOD_COUNT = 5
    BROKEN_COUNT = 4

    pg_connection.poll()
    assert GOOD_COUNT == len(pg_connection.notifies)
    assert GOOD_COUNT + BROKEN_COUNT == Notification.objects.count()
    assert 0 == Post.objects.count()

    simulate_listener_does_not_receive_notifications(pg_connection)
    with patch('pgpubsub.listen.POLL', False):
        listen(recover=True)
    pg_connection.poll()
    assert BROKEN_COUNT == Notification.objects.count()
    assert GOOD_COUNT == Post.objects.count()


@pytest.mark.django_db(transaction=True)
def test_media_insert_notify(pg_connection):
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert 'old' in stored_notification.payload
    assert 'new' in stored_notification.payload


@pytest.mark.django_db(transaction=True)
def test_persistent_notification_has_a_creation_timestamp(pg_connection, tx_start_time):
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.created_at >= tx_start_time


@pytest.mark.django_db(transaction=True)
def test_persistent_notification_has_a_db_version(pg_connection, tx_start_time):
    latest_app_migration = MigrationRecorder.Migration.objects.filter(app='tests').latest('id')
    Media.objects.create(name='avatar.jpg', content_type='image/png', size=15000)
    assert 1 == len(pg_connection.notifies)
    stored_notification = Notification.from_channel(channel=MediaTriggerChannel).get()
    assert stored_notification.db_version == latest_app_migration.id


@pytest.mark.django_db(transaction=True)
def test_lockable_notification_processor_when_notification_is_none(pg_connection, caplog):
    """Test the branch when notification is None due to another process holding the lock
    # todo: fix
    docker compose exec app pytest pgpubsub/tests/test_core.py::test_lockable_notification_processor_when_notification_is_none
    """
    from pgpubsub.listen import LockableNotificationProcessor
    from pgpubsub.compatibility import Notify
    from unittest.mock import patch, MagicMock
    import logging

    # Create a notification to trigger the channel
    media = Media.objects.create(name='test.jpg', content_type='image/png', size=1000)
    pg_connection.poll()
    notify = pg_connection.notifies.pop(0)

    # Mock the select_for_update query to return None (simulating locked notification)
    with patch('pgpubsub.models.Notification.objects.select_for_update') as mock_select:
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.first.return_value = None
        mock_select.return_value = mock_queryset

        # Also mock the second query that gets the locked notification
        with patch('pgpubsub.models.Notification.objects.select_for_update') as mock_select2:
            mock_queryset2 = MagicMock()
            mock_locked_notification = MagicMock()
            mock_locked_notification.__str__ = MagicMock(return_value='locked_notification')
            mock_queryset2.filter.return_value.first.return_value = mock_locked_notification

            # The second call should be the skip_locked=False query
            def side_effect(skip_locked=None):
                if skip_locked is True:
                    return mock_queryset
                elif skip_locked is False:
                    return mock_queryset2
                return mock_queryset

            mock_select.side_effect = side_effect
            mock_select2.side_effect = side_effect

            processor = LockableNotificationProcessor(notify, pg_connection)

            with caplog.at_level(logging.INFO):
                processor.process()

            # Verify the logging statements in the None branch
            log_messages = [record.message for record in caplog.records]
            assert any('Could not obtain a lock on notification' in msg for msg in log_messages)
            assert any('locked pgpubsub notification: locked_notification' in msg for msg in log_messages)
            assert any('postgres notification payload' in msg for msg in log_messages)
