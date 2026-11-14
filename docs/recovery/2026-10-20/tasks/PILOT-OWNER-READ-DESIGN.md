# Pilot 2 owner recovery browser design

Hypotheses for the absent pause button are a lost grant, an unhealthy owner after restoration,
or a view whose last successful read saw an uncertain owner. Read the grant and journal before
the outage. Force the already-supported Studio refresh during the outage, verify the real HTTP
owner state and the corresponding DOM, and compare the journal at the two boundaries. Then
restore the owner in the fixture and reproduce the existing test's expectation of a pause button.

The actual owner latches uncertainty until recovery. Restoring a monkeypatch sends no product
event. If the original route reads healthy again and the DOM then re-enables pause, exercise
the operator's existing refresh command after restoration. Keep the controls hidden until this
read. If that command fails, investigate the product at the HTTP/DOM seam instead. Do not change
timeouts, authority, polling policy or model activity to make a witness pass.

Run the English and Russian recovery cases and the automation browser module. Check that a
missing healthy reread reproduces the original absence of pause under the explicit schedule.
