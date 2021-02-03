CREATE TABLE IF NOT EXISTS `challenge_times` (
  `ID` smallint(6) NOT NULL AUTO_INCREMENT,
  `User` bigint(20) NOT NULL UNIQUE,
  `TimesLeft` tinyint(4) NOT NULL DEFAULT 5,
  PRIMARY KEY (`ID`)
) DEFAULT CHARSET = utf8;