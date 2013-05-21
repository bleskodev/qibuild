## Copyright (c) 2012, 2013 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

import qisrc.manifest
import qisrc.review

import pytest

import mock


def test_simple_read(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <repo project="foo/bar.git" src="lib/bar" branch="next" />
</manifest>
""")
    manifest = qisrc.manifest.Manifest(manifest_xml.strpath)

    assert len(manifest.repos) == 1
    bar = manifest.repos[0]
    assert bar.src == "lib/bar"
    assert bar.remote.url == "git@example.com:foo/bar.git"
    assert bar.default_branch == "next"

def test_no_matching_remote(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <repo project="foo/bar.git" src="lib/bar" remote="invalid" />
</manifest>
""")
    # pylint: disable-msg=E1101
    with pytest.raises(qisrc.manifest.ManifestError) as e:
        qisrc.manifest.Manifest(manifest_xml.strpath)
    assert e.value.message == "No matching remote: invalid for repo foo/bar.git"

def test_branch(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <repo project="bar.git" />
  <repo project="foo.git" branch="devel" />
</manifest>
""")
    manifest = qisrc.manifest.Manifest(manifest_xml.strpath)
    bar = manifest.repos[0]
    foo = manifest.repos[1]
    assert bar.default_branch == "master"
    assert foo.default_branch == "devel"

def test_invalid_group(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <repo project="foo.git" />
  <groups>
    <group name="foo-group">
      <project name="foo.git" />
      <project name="bar.git" />
    </group>
  </groups>

</manifest>
""")
    # pylint: disable-msg=E1101
    manifest = qisrc.manifest.Manifest(manifest_xml.strpath)
    with pytest.raises(qisrc.manifest.ManifestError) as e:
        manifest.get_repos(groups=["foo-group"])
    assert "foo-group" in str(e.value)
    assert "bar.git" in str(e.value)
    with pytest.raises(qisrc.manifest.ManifestError) as e:
        manifest.get_repos(groups=["mygroup"])
    assert "No such group: mygroup" in str(e.value)


def test_review_projects(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <remote name="gerrit" url="http://gerrit:8080" review="true" />
  <repo project="foo/bar.git" src="lib/bar" remote="gerrit" />
</manifest>
""")
    manifest = qisrc.manifest.Manifest(manifest_xml.strpath)
    assert len(manifest.repos) == 1
    bar = manifest.repos[0]
    assert bar.src == "lib/bar"
    assert bar.remote.url == "http://gerrit:8080/foo/bar.git"
    assert bar.review == True

def test_groups(tmpdir):
    manifest_xml = tmpdir.join("manifest.xml")
    manifest_xml.write(""" \
<manifest>
  <remote name="origin" url="git@example.com" />
  <repo project="qi/libqi.git" />
  <repo project="qi/libqimessaging.git" />
  <repo project="qi/naoqi.git" />

  <groups>
    <group name="qim">
      <project name="qi/libqi.git" />
      <project name="qi/libqimessaging.git" />
    </group>
  </groups>
</manifest>
""")
    manifest = qisrc.manifest.Manifest(manifest_xml.strpath)
    git_projects = manifest.get_repos(groups=["qim"])
    assert len(git_projects) == 2
    assert git_projects[0].remote.url == "git@example.com:qi/libqi.git"
    assert git_projects[1].remote.url == "git@example.com:qi/libqimessaging.git"


