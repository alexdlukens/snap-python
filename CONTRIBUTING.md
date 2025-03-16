# Developing this project

## Create a Release

I have automated releases to pypi.org from github releases.
To publish a new release, increment the version in `pyproject.toml`,
and make a corresponding github release

```bash
git tag -a v0.x.x -m "Release v0.x.x"
git push --tags
gh release create v0.x.x --title "Release v0.x.x"
```

The automation will build a wheel and push it to pypi

## Documentation

Documentation building is also automated through commits to the master branch.
When a new commit is created on the master branch, a pipeline will build the docs and publish to github pages.
