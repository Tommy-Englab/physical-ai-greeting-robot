# Copyright 2015 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ament_pep257.main import main
import pytest


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    # 日本語docstring方針（steering: communication）のため、英語前提の規約を除外する。
    #   D400: 1行目がピリオドで終わる（日本語は「。」で終わるため不可避）
    #   D1xx: docstring欠落系（簡潔なヘルパには付けない方針）
    rc = main(argv=[
        '.', 'test',
        '--add-ignore='
        'D100,D101,D102,D103,D104,D105,D205,D213,D400,D401,D403,D415',
    ])
    assert rc == 0, 'Found code style errors / warnings'
