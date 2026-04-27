package main

import (
  "testing"

  "github.com/stretchr/testify/require"
  "golang.org/x/mod/semver"
)

func TestVersion_Valid(t *testing.T) {
  require := require.New(t)
  require.True(semver.IsValid(version()), "version is valid semver")
}
