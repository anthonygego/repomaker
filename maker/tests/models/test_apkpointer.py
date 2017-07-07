import os
import shutil
from datetime import datetime
from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.test import TestCase, override_settings
from django.utils import timezone
from fdroidserver.update import get_all_icon_dirs

import maker.models.app
from maker.models import Apk, ApkPointer, RemoteApkPointer, App, RemoteApp, RemoteRepository, \
    Repository
from maker.storage import get_apk_file_path
from .. import TEST_DIR, TEST_FILES_DIR, TEST_PRIVATE_DIR, fake_repo_create


@override_settings(MEDIA_ROOT=TEST_DIR, PRIVATE_REPO_ROOT=TEST_PRIVATE_DIR)
class ApkPointerTestCase(TestCase):
    apk_file_name = 'test_1.apk'

    def setUp(self):
        # Create Repository
        self.repo = Repository.objects.create(user=User.objects.create(username='user2'))

        # Create APK
        self.apk = Apk.objects.create()

        # Attach a real APK file to the Apk
        file_path = os.path.join(TEST_FILES_DIR, self.apk_file_name)
        with open(file_path, 'rb') as f:
            self.apk.file.save(self.apk_file_name, File(f), save=True)

        # Create ApkPointer
        self.apk_pointer = ApkPointer(repo=self.repo)

        # Attach a real APK file to the pointer
        file_path = os.path.join(TEST_FILES_DIR, self.apk_file_name)
        with open(file_path, 'rb') as f:
            self.apk_pointer.file.save(self.apk_file_name, File(f), save=True)

    def tearDown(self):
        shutil.rmtree(TEST_DIR)

    def test_str(self):
        self.apk_pointer.app = App.objects.create(repo=self.repo, name='TestApp')
        self.apk_pointer.apk = Apk.objects.create()
        self.assertEqual('TestApp - 0 - user_2/repo_1/repo/test_1.apk', str(self.apk_pointer))

    def test_initialize(self):
        self.apk.initialize(self.repo)  # this calls self.apk_pointer.initialize()

        # assert that global APK file has been linked/copied properly
        self.assertEqual(get_apk_file_path(self.apk, self.apk_file_name), self.apk.file.name)
        self.assertTrue(os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.apk.file.name)))

        # get the created Apk object and assert that it has been created properly
        app = App.objects.get(pk=1)
        self.assertEqual(self.apk_pointer.repo, app.repo)
        self.assertEqual(self.apk.package_id, app.package_id)
        self.assertEqual(app.package_id, app.name)  # this apk has no name, so use fallback
        self.assertEqual([settings.LANGUAGE_CODE], list(app.get_available_languages()))

        # assert that the app icon has been created properly
        icon_name = app.package_id + '.' + str(self.apk.version_code) + '.png'
        self.assertTrue(app.icon.name.endswith(icon_name))
        self.assertTrue(os.path.isfile(app.icon.path))

    def test_initialize_reuses_existing_app(self):
        # create existing App object with same repo and package_id
        app = App.objects.create(repo=self.apk_pointer.repo,
                                 package_id='org.bitbucket.tickytacky.mirrormirror')

        # initialize the ApkPointer with its stored APK file
        self.apk.package_id = app.package_id
        self.apk_pointer.apk = self.apk
        self.apk_pointer.initialize({'type': 'apk', 'name': app.package_id, 'icons_src': {}})

        # assert that the App object was re-used
        self.assertTrue(len(App.objects.all()) == 1)
        self.assertEqual(app, self.apk_pointer.app)

        # assert that existing App object was updated
        app = App.objects.get(pk=app.pk)
        self.assertEqual('org.bitbucket.tickytacky.mirrormirror', app.name)
        self.assertTrue(app.icon)

    def test_initialize_non_apk(self):
        # overwrite APK file with image file
        self.apk.file.delete()
        file_path = os.path.join(TEST_FILES_DIR, 'test.png')
        with open(file_path, 'rb') as f:
            self.apk.file.save('test.png', File(f), save=True)

        # initialize the ApkPointer with its stored image file
        self.apk.initialize(self.repo)  # this calls self.apk_pointer.initialize()

        # assert that image was added properly
        self.assertEqual('test', self.apk.package_id)
        self.assertEqual(10, len(str(self.apk.version_code)))
        self.assertEqual(datetime.now().strftime('%Y-%m-%d'), self.apk.version_name)
        self.assertEqual(11575, self.apk.size)
        self.assertEqual('9b6acf7fa93477170b222bea2d0395fda2557f2ce953f138b011825f333ff02c',
                         self.apk.hash)
        self.assertEqual('sha256', self.apk.hash_type)

        # assert that image "app" was added properly
        apps = App.objects.all()
        self.assertEqual(1, apps.count())
        self.assertEqual(apps[0], ApkPointer.objects.get(apk=self.apk).app)  # pointer app
        self.assertEqual('test', apps[0].name)  # name
        self.assertEqual('test', apps[0].package_id)  # package ID
        self.assertEqual(maker.models.app.IMAGE, apps[0].type)  # app type
        self.assertEqual(settings.APP_DEFAULT_ICON, apps[0].icon.name)  # icon

    def test_icons_get_deleted_from_repo(self):
        # create the repository environment
        fake_repo_create(self.apk_pointer.repo)
        self.apk_pointer.apk = self.apk
        self.apk_pointer.apk.version_code = 1137

        # List with icon directories
        icon_name = \
            self.apk_pointer.apk.package_id + "." + str(self.apk_pointer.apk.version_code) + ".png"
        for icon_directory in get_all_icon_dirs(self.repo.get_repo_path()):
            icon = os.path.join(icon_directory, icon_name)
            with open(icon, 'wb') as f:
                f.write(b'foo')
            # Check that icons exist
            self.assertTrue(os.path.isfile(icon))

        # Delete app icons
        self.apk_pointer.delete()

        for icon_directory in get_all_icon_dirs(self.repo.get_repo_path()):
            icon = os.path.join(icon_directory, icon_name)
            # Check that icons do not exist
            self.assertFalse(os.path.isfile(icon))

    def test_link_file_from_apk(self):
        # delete pointer file and add one for apk
        self.apk_pointer.file.delete()
        self.apk_pointer.apk = Apk.objects.create()
        self.apk_pointer.apk.file.save('test.apk', BytesIO(b'foo'), save=True)

        # link pointer file from apk
        self.assertFalse(self.apk_pointer.file)
        self.apk_pointer.link_file_from_apk()
        self.assertTrue(self.apk_pointer.file)
        self.assertTrue(os.path.isfile(self.apk_pointer.file.path))

    def test_link_file_from_apk_only_when_no_file(self):
        file_path = self.apk_pointer.file.path
        self.assertTrue(os.path.isfile(file_path))

        self.apk_pointer.link_file_from_apk()  # linking should bail out, because file exists

        self.assertEqual(file_path, self.apk_pointer.file.path)


class RemoteApkPointerTestCase(TestCase):

    def setUp(self):
        self.repo = RemoteRepository.objects.get(pk=1)
        self.apk = Apk.objects.create(package_id='org.example', version_code=1337)
        date = datetime.fromtimestamp(0, timezone.utc)
        self.app = RemoteApp.objects.create(repo=self.repo, package_id='org.example',
                                            name='TestApp', last_updated_date=date)
        self.remote_apk_pointer = RemoteApkPointer.objects.create(apk=self.apk, app=self.app,
                                                                  url='test_url/test.apk')

    def test_str(self):
        self.assertEqual('TestApp - 1337 - test.apk', str(self.remote_apk_pointer))

    def test_pointer_check_when_deleted(self):
        self.assertTrue(Apk.objects.all().exists())
        self.remote_apk_pointer.delete()
        self.assertFalse(Apk.objects.all().exists())  # Apk got deleted, because no more pointers
