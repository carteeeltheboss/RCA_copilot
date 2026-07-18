Contributing to RCA Copilot
===========================

RCA Copilot follows the OpenStack collaborative development model. Changes
should be small, reviewed, tested, and accompanied by a release note when they
alter operators' or users' experience.

Development workflow
--------------------

1. Create a topic branch from ``main``.
2. Install test dependencies with ``python -m pip install tox``.
3. Run ``tox -e pep8,py311`` before proposing a change.
4. Add a reno note with ``reno new <slug>`` for significant changes.
5. Use a clear commit message and include ``Closes-Bug`` or ``Implements``
   trailers when applicable.

Developer Certificate of Origin
--------------------------------

Contributors certify that they have the right to submit their work by adding a
``Signed-off-by`` line as described by the Developer Certificate of Origin.

License
-------

The repository is MIT licensed. MIT is OSI approved and permits OpenStack
distribution, although Apache License 2.0 is the usual license for new
OpenStack-governed projects. Relicensing requires copyright-holder approval.
