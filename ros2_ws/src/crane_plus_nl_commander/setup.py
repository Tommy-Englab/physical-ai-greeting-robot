from setuptools import find_packages, setup

package_name = 'crane_plus_nl_commander'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'google-genai', 'pydantic>=2'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='ubuntu@todo.todo',
    description='自然言語指示をLLMで安全なプリセット計画(JSON)に変換し、検証後にCRANE+ V2へJointTrajectoryを送るコマンダ',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'nl_commander = crane_plus_nl_commander.nl_commander:main'
        ],
    },
)
