import { useNavigate } from "react-router-dom";
import { AppShell } from "../components/AppShell.js";
import { Button, Surface, Text } from "../components/primitives.js";

export function NotFoundScreen() {
  const navigate = useNavigate();
  return (
    <AppShell title="This page is not part of the demo">
      <Surface>
        <h1 className="re-list-title">This page is not part of the demo</h1>
        <Text role="body">Unknown routes do not create intents or contact suppliers.</Text>
        <Button id="unknown-home" variant="primary" onClick={() => navigate("/")}>
          Return to Intents
        </Button>
      </Surface>
    </AppShell>
  );
}
