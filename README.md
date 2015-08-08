# wikigenre

A foobar2000 companion designed to fetch genres.


## Installation

1.  Clone the repository:

    ```batch
    > git clone https://github.com/Perlence/wikigenre.git
    ```

2.  Install the package:

    ```batch
    > pip install .
    ```


## Usage

There are 3 modes of operation: *path*, *query* and *stdin*.

All modes differ in the way artist and album info is acquired. This info is used then to search Wikipedia for genres.

### Path mode

In *path mode* you specify glob so the program tries to open audio files located there, and get artist and album info from tags.

Example:

```batch
wikigenre "c:/music/The Beatles/*/*.mp3"
```

### Query mode

In *query mode* you pass the artist and album info in special form:

```
[artist - ]album(; [artist - ]album)*
```

Example:

```batch
> wikigenre -q "The Beatles - Abbey Road"
The Beatles - Abbey Road: Rock

> wikigenre -q "Abbey Road"
Abbey Road: Rock

> wikigenre -q "Abbey Road; Metallica - ...And Justice for All"
Abbey Road: Rock
Metallica - ...And Justice for All: Thrash Metal
```

### Stdin mode

I use *stdin mode* in conjecture with foobar2000.

* Select the tracks in the playlist.
* Press <kbd>Ctrl+C</kbd> to copy.
* Start `cmd.exe` and execute `wikigenre | clip`,
* Paste.
* Press <kbd>Enter</kbd> for a new line.
* Press <kbd>Ctrl+Z</kbd> for EOF.
  The program parses artist and album data from each line and proceeds to Wikipedia, then it redirects output to `clip`.
* Switch to foobar2000.
* Open **Track Properties** with <kbd>Alt+Enter</kbd>.
* Double click on **Genres** in the column **Name**.
* Select all.
* Paste.
